"""Sport-neutral paired prospective forecast evaluation (research-only).

Compares predictions to *frozen, paired* baselines without selecting winners
after outcomes are known. All provenance fields are declarations until the
underlying snapshots and rights are independently verified. No data network I/O.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
import json
import re
import sys
from urllib.parse import urlsplit


_ID = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]*:[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
_SHA = re.compile(r"^[a-fA-F0-9]{64}$")
_SPORT = re.compile(r"^[A-Z][A-Z0-9_]{1,19}$")
_MARKET = re.compile(r"^[a-z][a-z0-9_]*$")
_STATUSES = {"final", "void", "pending", "no_decision"}


def _id(value: object) -> bool:
    return isinstance(value, str) and bool(_ID.fullmatch(value))


def _sha(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA.fullmatch(value))


def _time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.utcoffset() is None:
            return None
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError, TypeError):
        return None


def _number(value: object) -> bool:
    # Enforce a realistic finite envelope and avoid huge-int->float overflows.
    # Units/stat vocabularies remain sport-adapter responsibilities.
    if type(value) is int:
        return abs(value) <= 1_000_000_000
    if type(value) is float:
        return isfinite(value) and abs(value) <= 1_000_000_000
    return False


def _url(value: object) -> bool:
    if not isinstance(value, str) or any(c.isspace() for c in value):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https" and bool(parsed.hostname)
            and parsed.username is None and parsed.password is None
        )
    except ValueError:
        return False


@dataclass(frozen=True)
class PairedEvaluation:
    structurally_valid: bool
    evaluation_complete: bool
    production_eligible: bool
    scoring_eligible: bool
    total_forecasts: int
    graded: int
    voided: int
    pending: int
    no_decision: int
    unique_graded_events: int
    model_mae: float | None
    baseline_mae: float | None
    paired_mae_improvement: float | None
    model_beats_baseline: int
    baseline_beats_model: int
    tied: int
    reasons: tuple[str, ...]
    independent_checks_required: tuple[str, ...] = (
        "frozen_manifest_receipt", "source_authenticity", "source_rights",
        "athlete_identity", "full_roster_coverage", "holdout_independence",
        "calibration_and_uncertainty", "owner_promotion_approval",
    )


def _invalid(reasons: list[str], code: str) -> None:
    if code not in reasons:
        reasons.append(code)


def evaluate_batch(document: object) -> PairedEvaluation:
    """Inspect a single-sport, single-market, single-model frozen cohort.

    The caller must supply the entire original forecast-ID inventory plus a
    settlement row for *each* forecast, including voids and pending outcomes.
    Neither hashes nor timestamp strings prove independent historical capture.
    Passing this structural audit never authorizes product scoring or betting.
    """
    reasons: list[str] = []
    forecasts: dict[str, dict] = {}
    settlements: dict[str, dict] = {}
    graded_errors: list[tuple[str, float, float, str]] = []
    status_counts = dict.fromkeys(("final", "void", "pending", "no_decision"), 0)

    if not isinstance(document, dict):
        _invalid(reasons, "batch_not_object")
        document = {}

    sport = document.get("sport")
    market = document.get("market")
    if not isinstance(sport, str) or _SPORT.fullmatch(sport) is None:
        _invalid(reasons, "sport_invalid")
    if not isinstance(market, str) or _MARKET.fullmatch(market) is None:
        _invalid(reasons, "market_invalid")
    if not _id(document.get("batch_id")):
        _invalid(reasons, "batch_id_invalid")
    if not _id(document.get("model_version")):
        _invalid(reasons, "model_version_invalid")
    if not _id(document.get("baseline_version")):
        _invalid(reasons, "baseline_version_invalid")
    if not _sha(document.get("frozen_manifest_sha256")):
        _invalid(reasons, "frozen_manifest_digest_missing")
    if not _sha(document.get("baseline_artifact_sha256")):
        _invalid(reasons, "baseline_artifact_digest_missing")
    if not _sha(document.get("evaluation_protocol_sha256")):
        _invalid(reasons, "evaluation_protocol_digest_missing")

    batch_frozen = _time(document.get("frozen_manifest_at_utc"))
    protocol_frozen = _time(document.get("evaluation_protocol_frozen_at_utc"))
    as_of = _time(document.get("evaluated_as_of_utc"))
    if batch_frozen is None or protocol_frozen is None or as_of is None:
        _invalid(reasons, "batch_timestamps_invalid")
    elif not protocol_frozen <= batch_frozen <= as_of:
        _invalid(reasons, "protocol_or_evaluation_order_invalid")

    entries = document.get("forecasts")
    if not isinstance(entries, list) or not entries:
        _invalid(reasons, "forecasts_missing")
        entries = []
    for n, entry in enumerate(entries):
        pre = f"forecast_{n}"
        if not isinstance(entry, dict):
            _invalid(reasons, pre + "_not_object")
            continue
        fid = entry.get("forecast_id")
        if not _id(fid):
            _invalid(reasons, pre + "_id_invalid")
            continue
        if fid in forecasts:
            _invalid(reasons, pre + "_duplicate_id")
            continue
        forecasts[fid] = entry

        eid, aid, tid = (entry.get("event_id"), entry.get("athlete_id"),
                         entry.get("team_id"))
        if (not _id(eid) or not isinstance(sport, str)
                or not eid.startswith(sport.lower() + ":")):
            _invalid(reasons, pre + "_event_id_invalid")
        if not _id(aid) or not _id(tid):
            _invalid(reasons, pre + "_athlete_or_team_id_invalid")
        if entry.get("market") != market:
            _invalid(reasons, pre + "_market_mismatch")
        start = _time(entry.get("scheduled_start_utc"))
        frozen = _time(entry.get("frozen_at_utc"))
        training = _time(entry.get("training_data_as_of_utc"))
        base_frozen = _time(entry.get("baseline_frozen_at_utc"))
        base_as_of = _time(entry.get("baseline_data_as_of_utc"))
        if start is None or frozen is None or training is None:
            _invalid(reasons, pre + "_times_invalid")
        elif not training <= frozen < start:
            _invalid(reasons, pre + "_hindsight_or_poststart")
        if base_frozen is None or base_as_of is None or frozen is None:
            _invalid(reasons, pre + "_baseline_times_invalid")
        elif not base_as_of <= base_frozen <= frozen:
            _invalid(reasons, pre + "_baseline_not_prefrozen")
        if start is not None and batch_frozen is not None and batch_frozen >= start:
            _invalid(reasons, pre + "_manifest_late")
        if frozen is not None and batch_frozen is not None and frozen > batch_frozen:
            _invalid(reasons, pre + "_forecast_after_manifest")
        for field in ("predicted_value", "baseline_value"):
            if not _number(entry.get(field)):
                _invalid(reasons, pre + "_" + field + "_invalid")

    # No analyst can drop a miss after a game and silently change the cohort.
    expected_ids = document.get("expected_forecast_ids")
    if not isinstance(expected_ids, list) or not expected_ids or not all(
            _id(value) for value in expected_ids):
        _invalid(reasons, "expected_id_inventory_invalid")
    elif len(expected_ids) != len(set(expected_ids)):
        _invalid(reasons, "expected_id_inventory_duplicates")
    elif set(expected_ids) != set(forecasts):
        _invalid(reasons, "expected_id_inventory_mismatch")

    # Reject repeated athlete-event-market opportunities hidden under new IDs.
    seen_opportunities: set[tuple[str, str, str, str]] = set()
    seen_player_teams: dict[tuple[str, str], str] = {}
    for entry in forecasts.values():
        key = (entry.get("event_id"), entry.get("athlete_id"),
               entry.get("team_id"), entry.get("market"))
        if not all(isinstance(v, str) for v in key):
            continue
        if key in seen_opportunities:
            _invalid(reasons, "duplicate_player_event_market")
        seen_opportunities.add(key)
        player_key = (key[0], key[1])
        if player_key in seen_player_teams and seen_player_teams[player_key] != key[2]:
            _invalid(reasons, "athlete_assigned_multiple_teams_in_event")
        seen_player_teams[player_key] = key[2]

    outcomes = document.get("settlements")
    if not isinstance(outcomes, list):
        _invalid(reasons, "settlements_missing")
        outcomes = []
    for n, entry in enumerate(outcomes):
        pre = f"settlement_{n}"
        if not isinstance(entry, dict):
            _invalid(reasons, pre + "_not_object")
            continue
        fid = entry.get("forecast_id")
        if not _id(fid):
            _invalid(reasons, pre + "_id_invalid")
            continue
        if fid in settlements:
            _invalid(reasons, pre + "_duplicate_id")
            continue
        settlements[fid] = entry
        forecast = forecasts.get(fid)
        if forecast is None:
            _invalid(reasons, pre + "_unmatched_forecast")
            continue
        if any(entry.get(k) != forecast.get(k) for k in
               ("event_id", "athlete_id", "team_id", "market")):
            _invalid(reasons, pre + "_identity_mismatch")
        status = entry.get("status")
        if not isinstance(status, str) or status not in _STATUSES:
            _invalid(reasons, pre + "_status_invalid")
            continue
        status_counts[status] += 1
        actual = entry.get("actual_value")
        if status == "final":
            if not _number(actual):
                _invalid(reasons, pre + "_actual_invalid")
        elif actual is not None:
            _invalid(reasons, pre + "_nonfinal_has_actual")

        if status == "pending":
            # Settlements must be explicit and cannot create future data by
            # filling an outcome or a known-after-the-event source receipt.
            if any(entry.get(k) is not None for k in (
                    "source_url", "published_at_utc", "captured_at_utc",
                    "raw_sha256")):
                _invalid(reasons, pre + "_pending_has_settlement_source")
        else:
            published = _time(entry.get("published_at_utc"))
            captured = _time(entry.get("captured_at_utc"))
            if not _url(entry.get("source_url")) or not _sha(entry.get("raw_sha256")):
                _invalid(reasons, pre + "_source_provenance_missing")
            if published is None or captured is None or published > captured:
                _invalid(reasons, pre + "_source_timestamps_invalid")
            if captured is not None and as_of is not None and captured > as_of:
                _invalid(reasons, pre + "_future_settlement")
            start = _time(forecast.get("scheduled_start_utc"))
            if status == "final" and (start is None or captured is None or
                                     captured <= start):
                _invalid(reasons, pre + "_final_before_start")

        if (status == "final" and _number(actual) and
                _number(forecast.get("predicted_value")) and
                _number(forecast.get("baseline_value"))):
            eid = forecast.get("event_id")
            if isinstance(eid, str):
                model_error = abs(forecast["predicted_value"] - actual)
                baseline_error = abs(forecast["baseline_value"] - actual)
                graded_errors.append((eid, model_error, baseline_error, fid))

    if set(settlements) != set(forecasts):
        _invalid(reasons, "settlement_inventory_mismatch")

    # An invalid manifest must never yield superficially credible metrics.
    valid = not reasons
    scored = sorted(graded_errors, key=lambda x: x[3]) if valid else []
    n = len(scored)
    model_mae = (sum(x[1] for x in scored) / n) if n else None
    baseline_mae = (sum(x[2] for x in scored) / n) if n else None
    improved = baseline_mae - model_mae if n else None
    return PairedEvaluation(
        structurally_valid=valid,
        evaluation_complete=valid and status_counts["pending"] == 0,
        production_eligible=False,
        scoring_eligible=False,
        total_forecasts=len(forecasts),
        graded=status_counts["final"] if valid else 0,
        voided=status_counts["void"] if valid else 0,
        pending=status_counts["pending"] if valid else 0,
        no_decision=status_counts["no_decision"] if valid else 0,
        unique_graded_events=len({x[0] for x in scored}),
        model_mae=model_mae,
        baseline_mae=baseline_mae,
        paired_mae_improvement=improved,
        model_beats_baseline=sum(x[1] < x[2] for x in scored),
        baseline_beats_model=sum(x[2] < x[1] for x in scored),
        tied=sum(x[1] == x[2] for x in scored),
        reasons=tuple(reasons),
    )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m research.quality.paired_evaluation BATCH.json",
              file=sys.stderr)
        return 2
    try:
        payload = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": "batch_unreadable", "detail": str(exc)}))
        return 2
    result = evaluate_batch(payload)
    print(json.dumps(asdict(result), indent=2))
    return 0 if result.structurally_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
