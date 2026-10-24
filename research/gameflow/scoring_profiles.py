"""Aggregate final NBA game-flow files into evidence-only player profiles.

This module does not generate forecasts or Play-grade selections.
"""
import json
import os
from collections import defaultdict
from pathlib import Path

BASE = Path(os.environ.get("COURTSIDE_AGENCY_BASE", str(Path(__file__).resolve().parents[2])))
GF = BASE / "data" / "gameflow" / "nba"
NOTES = BASE / "data" / "gameflow" / "pattern_notes.jsonl"
OUT = BASE / "data" / "scoring_profiles.json"

# Publicly retracted v1 detector artifacts (see research/docs/GAMEFLOW_FINDINGS_2026-10-23.md).
RETRACTED_SURGE_EVENTS = {"401909840"}


def mins(value):
    """Parse ESPN MM:SS playing time without silently truncating seconds."""
    try:
        value = str(value)
        if ":" in value:
            m, s = value.split(":", 1)
            return int(m) + int(s) / 60
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def aggregate(game_files, notes_path):
    """Return (profiles, diagnostics) using only distinct final event snapshots.

    Notes are never allowed to create a player, team, or game absent from the
    final snapshots. Profile keys are team-qualified to prevent name collisions.
    """
    players = defaultdict(lambda: {"games": 0, "starts": 0, "min": 0.0,
                                   "pts": 0, "fga": 0, "pf": 0,
                                   "capped": 0, "cannibal": 0, "victim": 0})
    final_events = set()
    event_rosters = {}
    skipped_nonfinal = 0
    skipped_duplicate = 0
    for path in sorted(game_files):
        game = json.loads(Path(path).read_text())
        if game.get("league") != "nba" or game.get("status") != "Final":
            skipped_nonfinal += 1
            continue
        event = str(game.get("event", ""))
        if not event:
            skipped_nonfinal += 1
            continue
        if event in final_events:
            skipped_duplicate += 1
            continue
        final_events.add(event)
        event_rosters[event] = set()
        for p in game.get("players", []):
            team, name = p.get("team"), p.get("name")
            if not team or not name:
                continue
            if (team, name) in event_rosters[event]:
                continue
            event_rosters[event].add((team, name))
            d = players[(team, name)]
            d["games"] += 1
            d["starts"] += int(bool(p.get("starter")))
            d["min"] += mins(p.get("min"))
            d["pts"] += int(p.get("pts") or 0)
            d["fga"] += int(p.get("fga") or 0)
            d["pf"] += int(p.get("pf") or 0)

    seen_notes = set()
    skipped_unverified_notes = 0
    skipped_retracted = 0
    if Path(notes_path).exists():
        for line in Path(notes_path).read_text().splitlines():
            try:
                entry = json.loads(line)
            except (ValueError, TypeError):
                skipped_unverified_notes += 1
                continue
            event = str(entry.get("event", ""))
            if entry.get("league") != "nba" or event not in final_events:
                skipped_unverified_notes += 1
                continue
            for note in entry.get("notes", []):
                kind = note.get("type")
                team = note.get("team")
                if kind == "bench_usage_surge" and event in RETRACTED_SURGE_EVENTS:
                    skipped_retracted += 1
                    continue
                if kind == "foul_trouble_cap":
                    player = note.get("player")
                    key = (team, player)
                    dedupe = (event, kind, team, player)
                    if key not in event_rosters[event] or dedupe in seen_notes:
                        continue
                    seen_notes.add(dedupe)
                    players[key]["capped"] += 1
                elif kind == "bench_usage_surge":
                    bench, starter = note.get("bench_player"), note.get("slot_starter")
                    bench_key, starter_key = (team, bench), (team, starter)
                    dedupe = (event, kind, team, bench)
                    if bench_key not in event_rosters[event] or dedupe in seen_notes:
                        continue
                    seen_notes.add(dedupe)
                    players[bench_key]["cannibal"] += 1
                    if starter_key in event_rosters[event]:
                        players[starter_key]["victim"] += 1

    board = {}
    for (team, name), d in players.items():
        if not d["games"] or d["min"] < 20:
            continue
        pf36 = 36 * d["pf"] / d["min"]
        board[f"{team}|{name}"] = {
            "name": name, "team": [team], "games": d["games"],
            "starts": d["starts"], "min_pg": round(d["min"] / d["games"], 1),
            "pts_pg": round(d["pts"] / d["games"], 1),
            "fga_per_min": round(d["fga"] / d["min"], 2),
            "pf_per36": round(pf36, 1),
            "capped_events": d["capped"], "cannibal_events": d["cannibal"],
            "victim_events": d["victim"], "foul_risk": pf36 >= 4.8,
        }
    diagnostics = {
        "games_used": len(final_events),
        "games_skipped_nonfinal": skipped_nonfinal,
        "games_skipped_duplicate": skipped_duplicate,
        "notes_skipped_unverified": skipped_unverified_notes,
        "surge_notes_skipped_retracted": skipped_retracted,
        "profile_identity": "team|name (not stable athlete ID)",
        "prediction_authority": "EVIDENCE_ONLY",
    }
    return board, diagnostics


def main():
    board, diagnostics = aggregate(GF.glob("*/*.json"), NOTES)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({**diagnostics, "players": board}, indent=2))
    print(f"final games used: {diagnostics['games_used']}; "
          f"players profiled: {len(board)}; "
          f"retracted surges skipped: {diagnostics['surge_notes_skipped_retracted']}")
    for label, rows in (
        ("FOUL RISK (observed, not causal)", sorted(board.items(), key=lambda x: (-x[1]["capped_events"], -x[1]["pf_per36"]))[:10]),
        ("BENCH SURGES (observed, not predictive)", sorted(board.items(), key=lambda x: -x[1]["cannibal_events"])[:10]),
        ("USAGE VICTIMS (observed, not predictive)", sorted(board.items(), key=lambda x: -x[1]["victim_events"])[:10]),
    ):
        print(f"\n== {label} ==")
        for key, p in rows:
            print(f"  {key}: {p['pts_pg']} pts/g, {p['min_pg']} min/g")


if __name__ == "__main__":
    main()
