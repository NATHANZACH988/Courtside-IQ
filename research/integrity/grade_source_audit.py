"""Read-only audit for NBA prediction-to-final grading joins (research only).

Checks the actual watcher envelope before a name-keyed legacy grader consumes
it. This module never writes or alters a grade, changes scoring rules, or
asserts source authenticity. A clean structural result is NOT Play eligibility.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import sys

_EVENT = re.compile(r"^[0-9]{6,12}$")
_SHA = re.compile(r"^[a-fA-F0-9]{64}$")
_ALLOWED = {"FOUL_CAP", "CANNIBAL", "VICTIM", "STEADY"}


@dataclass(frozen=True)
class GradeSourceAudit:
    event_id: str | None
    player: str | None
    safe_for_legacy_grader: bool
    source_independently_verified: bool
    production_scoring_authorized: bool
    final_margin: int | None
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def _stamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.tzinfo is not None and dt.utcoffset() is not None
    except (ValueError, OverflowError, TypeError):
        return False


def audit_pair(prediction: object, final: object) -> GradeSourceAudit:
    """Inspect one frozen prediction and one purported ESPN watcher final.

    The legacy grader matches player display names without checking team,
    ignores the watcher's `segment_scores` margin, and accepts foul notes
    without verifying retraction status. This audit catches known unsafe
    cases; it does not repair them or change historical grades.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(prediction, dict):
        prediction = {}
        errors.append("prediction_not_object")
    if not isinstance(final, dict):
        final = {}
        errors.append("final_not_object")

    eid = prediction.get("event_id")
    name = prediction.get("player")
    team = prediction.get("team")
    opponent = prediction.get("opponent")
    mech = prediction.get("mechanism")
    if not isinstance(eid, str) or not _EVENT.fullmatch(eid):
        errors.append("event_id_not_valid_espn_nba_id")
    if not isinstance(name, str) or not name.strip():
        errors.append("player_name_missing")
    if not isinstance(team, str) or not team.strip():
        errors.append("prediction_team_missing")
    if not isinstance(opponent, str) or not opponent.strip() or opponent == team:
        errors.append("prediction_opponent_invalid")
    if not isinstance(mech, str) or mech not in _ALLOWED:
        errors.append("unknown_mechanism")
    if not isinstance(final.get("event"), (str, int)) or str(final["event"]) != eid:
        errors.append("final_event_mismatch")
    if final.get("league") != "nba":
        errors.append("final_league_not_nba")
    status = final.get("status")
    if not isinstance(status, str) or not status.lower().startswith("final"):
        errors.append("final_not_final")

    scores = final.get("teams")
    margin: int | None = None
    if (not isinstance(scores, dict) or len(scores) != 2
            or not all(isinstance(k, str) and k for k in scores)
            or not all(type(v) is int and v >= 0 for v in scores.values())):
        errors.append("final_team_scores_invalid")
    else:
        if team not in scores or opponent not in scores:
            errors.append("prediction_matchup_not_in_final")
        values = list(scores.values())
        margin = abs(values[0] - values[1])

    players = final.get("players")
    if not isinstance(players, list):
        errors.append("final_players_not_list")
        players = []
    elif any(not isinstance(p, dict) for p in players):
        errors.append("final_player_not_object")
        players = [p for p in players if isinstance(p, dict)]

    if isinstance(scores, dict):
        if any(p.get("team") not in scores for p in players):
            errors.append("final_player_team_not_in_matchup")

    # The legacy code uses next(player for player if player['name']==name).
    # Same-name athletes on opposite teams or duplicate rows can be silently
    # attributed to the wrong player, changing HIT/MISS without a warning.
    matching = [p for p in players if p.get("name") == name] if isinstance(name, str) else []
    if len(matching) > 1:
        errors.append("ambiguous_name_only_player_join")
    elif len(matching) == 1:
        if matching[0].get("team") != team:
            errors.append("player_team_mismatch_in_final")
        if not matching[0].get("athlete_id"):
            warnings.append("stable_athlete_id_unavailable")
    else:
        warnings.append("player_absent_from_final_box_no_decision_expected")

    notes = final.get("notes", [])
    if not isinstance(notes, list):
        errors.append("final_notes_not_list")
        notes = []
    for i, note in enumerate(notes):
        if not isinstance(note, dict):
            errors.append(f"note_{i}_not_object")
            continue
        # Original FOUL_CAP checks only the player name and substring 'foul'.
        if mech == "FOUL_CAP" and note.get("player") == name and (
                "foul" in str(note.get("type", ""))):
            if note.get("team") != team:
                errors.append("foul_note_wrong_or_missing_team")
            if note.get("retracted") is True or str(note.get("status", "")).lower() in (
                    "retracted", "withdrawn", "superseded"):
                errors.append("foul_note_retracted_but_legacy_grader_counts_it")
            if not note.get("source_id") and not note.get("source_sha256"):
                warnings.append("foul_note_provenance_not_attached")

    # The watcher writes 'teams' and 'segment_scores', not 'segments'.
    # The legacy CANNIBAL grade tries 'segments' and therefore silently
    # skips the <20-point blowout condition on actual watcher files.
    if mech == "CANNIBAL":
        if not isinstance(final.get("segments"), list) or not final["segments"]:
            errors.append("legacy_cannibal_blownout_gate_skipped")
        else:
            # Even with a segments field, the legacy sum(home-away) needs
            # independently validated semantics before relying on the gate.
            warnings.append("legacy_segment_margin_semantics_unverified")
        if margin is not None and margin >= 20:
            errors.append("cannibal_final_margin_at_least_20")

    # The watcher does not currently attach immutable raw ESPN receipts.
    # A supplied digest or URL is only a declaration, not verification.
    if (not isinstance(final.get("source_url"), str)
            or not final["source_url"].startswith("https://")
            or not _stamp(final.get("captured_at_utc"))
            or not isinstance(final.get("raw_sha256"), str)
            or not _SHA.fullmatch(final["raw_sha256"])):
        warnings.append("final_source_receipt_not_complete")
    else:
        warnings.append("source_receipt_claim_not_independently_verified")

    return GradeSourceAudit(
        event_id=eid if isinstance(eid, str) else None,
        player=name if isinstance(name, str) else None,
        safe_for_legacy_grader=not errors,
        source_independently_verified=False,
        production_scoring_authorized=False,
        final_margin=margin,
        errors=tuple(dict.fromkeys(errors)),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def audit_batch(predictions: object, finals: object) -> dict:
    """Read-only batch review; finals are explicitly supplied, never fetched.

    Missing final is PENDING, not an invented miss. Every prediction remains
    in the denominator, even if its source is unsafe.
    """
    if not isinstance(predictions, dict) or predictions.get("frozen") is not True:
        return {"valid": False, "errors": ["batch_not_frozen"],
                "total": 0, "pending": 0, "unsafe": 0,
                "source_independently_verified": False,
                "production_scoring_authorized": False, "pairs": []}
    entries = predictions.get("predictions")
    if not isinstance(entries, list) or not entries or not isinstance(finals, dict):
        return {"valid": False, "errors": ["batch_inventory_invalid"],
                "total": len(entries) if isinstance(entries, list) else 0,
                "pending": 0, "unsafe": 0,
                "source_independently_verified": False,
                "production_scoring_authorized": False, "pairs": []}
    reports: list[dict] = []
    pending = unsafe = 0
    for index, entry in enumerate(entries):
        eid = entry.get("event_id") if isinstance(entry, dict) else None
        if not isinstance(eid, str) or not _EVENT.fullmatch(eid):
            reports.append({"index": index, "event_id": eid if isinstance(eid, str) else None,
                            "errors": ["invalid_event_id"], "safe_for_legacy_grader": False})
            unsafe += 1
            continue
        if eid not in finals:
            reports.append({"index": index, "event_id": eid,
                            "pending": True, "errors": []})
            pending += 1
            continue
        result = audit_pair(entry, finals[eid])
        reports.append({"index": index, **asdict(result)})
        if not result.safe_for_legacy_grader:
            unsafe += 1
    return {"valid": unsafe == 0, "errors": [],
            "total": len(entries), "pending": pending, "unsafe": unsafe,
            "source_independently_verified": False,
            "production_scoring_authorized": False, "pairs": reports}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: python -m research.integrity.grade_source_audit FROZEN.json FINALS_BY_EVENT.json",
              file=sys.stderr)
        return 2
    try:
        frozen = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        finals = json.loads(Path(args[1]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": "input_unreadable", "detail": str(exc)}))
        return 2
    result = audit_batch(frozen, finals)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] and result["pending"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
