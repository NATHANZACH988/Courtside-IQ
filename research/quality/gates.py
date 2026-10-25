"""Fail-closed, sport-neutral structural audit of research handoff manifests.

This audits declared evidence, NOT its authenticity, licensing, model accuracy,
commercial data rights, or release authorization. No external dependencies.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*:[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
SPORT = re.compile(r"^[A-Z][A-Z0-9_]{1,19}$")
RIGHTS = {"unverified", "restricted", "licensed"}


@dataclass(frozen=True)
class Audit:
    schema_version: int
    source_structure_complete: bool
    prospective_record_complete: bool
    evaluation_record_complete: bool
    production_authorized: bool
    independent_reviews_required: tuple[str, ...]
    reasons: tuple[str, ...]


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        return None
    return stamp.astimezone(timezone.utc)


def _digest(value: object) -> bool:
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def _count(value: object) -> bool:
    return type(value) is int and value >= 0


def _url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not any(c.isspace() for c in value)
        )
    except ValueError:
        return False


def audit_manifest(raw: object) -> Audit:
    """Assess evidence completeness without promoting findings into scoring.

    The record is treated as a collection of *claims*. In particular, captured_at
    and hashes are not independent proof of when or what was actually captured.
    """
    if not isinstance(raw, dict):
        return Audit(1, False, False, False, False,
                     ("source_authenticity", "data_rights", "independent_review",
                      "owner_release_approval"), ("manifest_not_object",))

    source_errors: list[str] = []
    forecast_errors: list[str] = []
    evaluation_errors: list[str] = []
    if type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
        source_errors.append("unsupported_schema_version")
    sport = raw.get("sport")
    if not isinstance(sport, str) or not SPORT.fullmatch(sport):
        source_errors.append("sport_missing_or_invalid")
    study = raw.get("study_id")
    if not isinstance(study, str) or not IDENTIFIER.fullmatch(study):
        source_errors.append("study_id_not_stable")
    hypothesis = raw.get("hypothesis")
    if not isinstance(hypothesis, str) or len(hypothesis.strip()) < 10:
        source_errors.append("hypothesis_missing")

    sources = raw.get("sources")
    parsed_sources: list[tuple[datetime, datetime]] = []
    if not isinstance(sources, list) or not sources:
        source_errors.append("sources_missing")
        sources = []
    seen: set[str] = set()
    for index, source in enumerate(sources):
        prefix = f"source_{index}"
        if not isinstance(source, dict):
            source_errors.append(f"{prefix}_not_object")
            continue
        sid = source.get("source_id")
        if not isinstance(sid, str) or not IDENTIFIER.fullmatch(sid):
            source_errors.append(f"{prefix}_id_invalid")
        elif sid in seen:
            source_errors.append(f"{prefix}_duplicate_id")
        else:
            seen.add(sid)
        if not _url(source.get("url")):
            source_errors.append(f"{prefix}_url_invalid")
        if not _digest(source.get("raw_sha256")):
            source_errors.append(f"{prefix}_raw_digest_missing")
        if source.get("rights_status") not in RIGHTS:
            source_errors.append(f"{prefix}_rights_status_missing")
        published = _timestamp(source.get("published_at_utc"))
        captured = _timestamp(source.get("captured_at_utc"))
        if published is None or captured is None:
            source_errors.append(f"{prefix}_timestamps_invalid")
        elif published > captured:
            source_errors.append(f"{prefix}_published_after_capture")
        else:
            parsed_sources.append((published, captured))

    freeze = raw.get("freeze")
    cutoff = start = None
    if not isinstance(freeze, dict):
        forecast_errors.append("freeze_missing")
    else:
        cutoff = _timestamp(freeze.get("as_of_utc"))
        start = _timestamp(freeze.get("event_start_utc"))
        if cutoff is None or start is None or cutoff >= start:
            forecast_errors.append("freeze_not_before_event")
        if not _digest(freeze.get("artifact_sha256")):
            forecast_errors.append("freeze_artifact_digest_missing")
        event = freeze.get("event_id")
        if (not isinstance(event, str) or not IDENTIFIER.fullmatch(event)
                or not isinstance(sport, str)
                or not event.startswith(sport.lower() + ":")):
            forecast_errors.append("freeze_event_id_invalid")
        if cutoff is not None:
            if len(parsed_sources) != len(sources):
                forecast_errors.append("freeze_source_chronology_unverifiable")
            elif any(published > cutoff or captured > cutoff
                     for published, captured in parsed_sources):
                forecast_errors.append("freeze_uses_future_source")

    coverage = raw.get("coverage")
    if not isinstance(coverage, dict):
        forecast_errors.append("coverage_missing")
    else:
        eligible = coverage.get("eligible")
        screened = coverage.get("screened")
        excluded = coverage.get("excluded")
        unresolved = coverage.get("unresolved")
        if not all(_count(value) for value in
                   (eligible, screened, excluded, unresolved)):
            forecast_errors.append("coverage_counts_invalid")
        elif eligible == 0 or screened + excluded + unresolved != eligible:
            forecast_errors.append("coverage_does_not_reconcile")
        if coverage.get("rejection_reasons_recorded") is not True:
            forecast_errors.append("rejection_ledger_missing")
        # Unresolved cases may remain in the research ledger, but never
        # silently count as screened or as a qualified recommendation.

    evaluation = raw.get("evaluation")
    if not isinstance(evaluation, dict):
        evaluation_errors.append("evaluation_missing")
    else:
        predicted = evaluation.get("frozen_predictions")
        graded = evaluation.get("graded")
        voided = evaluation.get("voided")
        pending = evaluation.get("pending")
        holdout = evaluation.get("holdout_events")
        if not all(_count(v) for v in (predicted, graded, voided, pending, holdout)):
            evaluation_errors.append("evaluation_counts_invalid")
        else:
            if predicted == 0 or graded == 0 or holdout == 0:
                evaluation_errors.append("evaluation_sample_missing")
            if graded + voided + pending != predicted:
                evaluation_errors.append("evaluation_denominator_mismatch")
            if pending:
                evaluation_errors.append("evaluation_still_pending")
        if not _digest(evaluation.get("report_sha256")):
            evaluation_errors.append("evaluation_report_digest_missing")
        if not _digest(evaluation.get("protocol_sha256")):
            evaluation_errors.append("evaluation_protocol_digest_missing")
        protocol_at = _timestamp(evaluation.get("protocol_frozen_at_utc"))
        report_at = _timestamp(evaluation.get("report_generated_at_utc"))
        if protocol_at is None or cutoff is None or protocol_at > cutoff:
            evaluation_errors.append("evaluation_protocol_not_prefrozen")
        if report_at is None or start is None or report_at < start:
            evaluation_errors.append("evaluation_report_before_event")
        if protocol_at is not None and report_at is not None and report_at < protocol_at:
            evaluation_errors.append("evaluation_report_before_protocol")

    source_ok = not source_errors
    prospective_ok = source_ok and not forecast_errors
    evaluation_ok = prospective_ok and not evaluation_errors
    return Audit(
        schema_version=1,
        source_structure_complete=source_ok,
        prospective_record_complete=prospective_ok,
        evaluation_record_complete=evaluation_ok,
        production_authorized=False,
        independent_reviews_required=(
            "source_authenticity", "data_rights", "roster_and_identity",
            "backtest_methodology", "independent_review", "owner_release_approval"
        ),
        reasons=tuple(source_errors + forecast_errors + evaluation_errors),
    )


def main(argv: list[str] | None = None) -> int:
    """CLI: python -m research.quality.gates MANIFEST.json [source|prospective|evaluation]."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) not in (1, 2) or (len(args) == 2 and args[1] not in
                                  ("source", "prospective", "evaluation")):
        print("usage: python -m research.quality.gates FILE.json [source|prospective|evaluation]",
              file=sys.stderr)
        return 2
    target = args[1] if len(args) == 2 else "source"
    try:
        raw = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": "manifest_unreadable", "detail": str(exc)}))
        return 2
    report = audit_manifest(raw)
    print(json.dumps(asdict(report), indent=2))
    return 0 if {
        "source": report.source_structure_complete,
        "prospective": report.prospective_record_complete,
        "evaluation": report.evaluation_record_complete,
    }[target] else 1


if __name__ == "__main__":
    raise SystemExit(main())
