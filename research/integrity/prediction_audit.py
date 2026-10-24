"""Read-only consistency audit for frozen prospective NBA prediction logs.

A passing audit does NOT verify rosters, injuries, market prices, source
licensing, season-bank requirements, or forecasting performance.
"""
import argparse
from collections import defaultdict
from datetime import datetime
import json

REQUIRED = ("player", "team", "opponent", "event_id", "tip_utc",
            "logged_at_utc", "mechanism", "direction")
DIRECTIONS = {"FOUL_CAP": "DOWN", "CANNIBAL": "UP",
              "VICTIM": "DOWN", "STEADY": "UP"}


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("missing timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone required")
    return parsed


def audit(doc):
    errors, warnings = [], []
    entries = doc.get("predictions")
    if doc.get("frozen") is not True:
        errors.append("log_not_frozen")
    if not isinstance(entries, list):
        return {"errors": errors + ["predictions_not_list"], "warnings": [],
                "counts": {}, "prop_ready": False}
    try:
        built = timestamp(doc.get("built_at_utc"))
    except (ValueError, TypeError):
        errors.append("invalid_build_timestamp")
        built = None

    seen, by_player, by_name, by_event = set(), defaultdict(set), defaultdict(set), defaultdict(set)
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            errors.append(f"entry_{i}:not_object")
            continue
        missing = [k for k in REQUIRED if not isinstance(e.get(k), str) or not e[k].strip()]
        if missing:
            errors.append(f"entry_{i}:missing_{','.join(missing)}")
            continue
        mech = e["mechanism"]
        if mech not in DIRECTIONS or e["direction"] != DIRECTIONS[mech]:
            errors.append(f"entry_{i}:invalid_mechanism_direction")
        try:
            tip, logged = timestamp(e["tip_utc"]), timestamp(e["logged_at_utc"])
            if logged >= tip:
                errors.append(f"entry_{i}:not_logged_before_tip")
            if built is not None and built >= tip:
                errors.append(f"entry_{i}:build_not_before_tip")
            if built is not None and logged > built:
                errors.append(f"entry_{i}:logged_after_build")
        except (ValueError, TypeError):
            errors.append(f"entry_{i}:invalid_timestamp")
        if e.get("grade") is not None:
            errors.append(f"entry_{i}:frozen_log_contains_grade")
        key = (e["event_id"], e["team"], e["player"], mech)
        if key in seen:
            errors.append(f"entry_{i}:duplicate_prediction")
        seen.add(key)
        by_player[key[:3]].add(e["direction"])
        by_name[e["player"]].add(e["team"])
        by_event[e["event_id"]].add((e["team"], e["opponent"]))
        if not isinstance(e.get("basis"), str) or not e["basis"].strip():
            warnings.append(f"entry_{i}:missing_evidence_basis")
        if not e.get("source_url") or not e.get("source_observed_at_utc"):
            warnings.append(f"entry_{i}:missing_per_prediction_source_provenance")

    conflicts = ["|".join(k) for k, directions in by_player.items() if len(directions) > 1]
    if conflicts:
        warnings.append("opposite_direction_hypotheses_require_resolution")
    multi_team = sorted(n for n, teams in by_name.items() if len(teams) > 1)
    if multi_team:
        warnings.append("player_name_assigned_multiple_teams_requires_identity_review")
    for event, pairs in by_event.items():
        if any(team == opp for team, opp in pairs):
            errors.append(f"event_{event}:self_opponent")
        if len({frozenset(pair) for pair in pairs}) > 1:
            errors.append(f"event_{event}:inconsistent_matchup")
    if doc.get("games") != len(by_event):
        warnings.append("declared_game_count_differs_from_games_with_predictions")
    warnings.append("external_roster_injury_market_and_backtest_gates_unverified")
    return {"errors": errors, "warnings": warnings,
            "counts": {"entries": len(entries), "games_with_predictions": len(by_event),
                       "opposite_direction_players": len(conflicts),
                       "players_assigned_multiple_teams": len(multi_team)},
            "contradictions": conflicts, "multi_team_names": multi_team,
            "prop_ready": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Frozen prediction JSON; never modified")
    args = parser.parse_args()
    with open(args.path, encoding="utf-8") as file:
        result = audit(json.load(file))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
