#!/usr/bin/env python3
"""Capture a completed ESPN game into an attributed fixture + coaching bundle.

Usage:
  PYTHONPATH=. python3 scripts/capture_live_game.py --event-id 401909848
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.coaching.pbp import (
    build_provenance,
    extract_foul_states,
    extract_hot_cold_from_shots,
    extract_substitutions,
)
from research.coaching.rotations import leave_one_out_accuracy, predict_replacements
from research.coaching.schemas import FatigueProxy, GameStateBundle, PlayerGrade
from research.providers.espn import (
    LiveFetchError,
    fetch_game_summary,
    normalize_tipoff,
    parse_box_players,
    parse_game_meta,
)


def build_fatigue(players: list[dict], game_id: str) -> list[FatigueProxy]:
    out = []
    for p in players:
        minutes = float(p["minutes"])
        # Heuristic only — stint lengths need full stint reconstruction
        fatigue = min(1.0, max(0.0, (minutes - 24.0) / 20.0))
        out.append(
            FatigueProxy(
                player_id=p["player_id"],
                game_id=game_id,
                minutes=minutes,
                stint_count=0,
                longest_stint_seconds=None,
                back_to_back=False,
                fatigue_index=round(fatigue, 3),
                verification="inferred",
                notes=("Minutes-based fatigue proxy only; not heart-rate or tracking.",),
            )
        )
    return out


def build_simple_grades(players: list[dict], game_id: str) -> list[PlayerGrade]:
    """Transparent box-informed role grades — not film grades."""
    grades = []
    for p in players:
        if p["minutes"] < 5:
            continue
        pts = p["PTS"]
        # crude efficiency-ish outcome score scaled to minutes
        per_min = pts / max(p["minutes"], 1)
        box = min(100.0, round(40 + per_min * 40 + p["AST"] * 2 + p["REB"], 1))
        foul_pen = min(15.0, p["PF"] * 3.0)
        decision = max(0.0, 70.0 - foul_pen - p["TOV"] * 4)
        grades.append(
            PlayerGrade(
                player_id=p["player_id"],
                game_id=game_id,
                role="starter" if p.get("starter") else "bench",
                offense_grade=box,
                defense_grade=round(55 + p["STL"] * 5 + p["BLK"] * 5 - p["PF"] * 2, 1),
                decision_grade=round(decision, 1),
                box_outcome_grade=box,
                evidence_coverage=0.35,  # box + PBP only
                verification="inferred",
                notes=(
                    "No tracking/film; coverage intentionally low.",
                    "Decision grade penalizes fouls/turnovers only.",
                ),
            )
        )
    return grades


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", required=True)
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / "fixtures" / "box_scores" / "live_captures"),
    )
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        doc = fetch_game_summary(args.event_id)
    except LiveFetchError as exc:
        print(f"SKIP live capture: {exc}", file=sys.stderr)
        return 2

    meta = parse_game_meta(doc.payload)
    tip = normalize_tipoff(meta.get("scheduled_tipoff_utc"))
    meta["scheduled_tipoff_utc"] = tip
    players = parse_box_players(doc.payload)
    game_id = meta["game_id"]

    fixture = {
        "fixture_id": f"live_{args.event_id}",
        **meta,
        "source_url": doc.source_url,
        "fetched_at_utc": doc.fetched_at_utc,
        "note": (
            "Live-captured ESPN public summary for Courtside IQ beta testing. "
            "Commercial redistribution rights not verified for production."
        ),
        "players": players,
    }

    subs = extract_substitutions(game_id, doc.payload)
    fouls = extract_foul_states(game_id, doc.payload)
    hot_cold = extract_hot_cold_from_shots(game_id, doc.payload)
    bundle = GameStateBundle(
        game_id=game_id,
        provenance=build_provenance(doc.source_url, doc.fetched_at_utc),
        substitutions=subs,
        foul_events=fouls,
        fatigue=build_fatigue(players, game_id),
        hot_cold=hot_cold,
        grades=build_simple_grades(players, game_id),
    )
    rotation = [f.to_dict() for f in predict_replacements(subs)]
    loo = leave_one_out_accuracy(subs)

    fixture_path = out_dir / f"{args.event_id}.json"
    coaching_path = out_dir / f"{args.event_id}.coaching.json"
    fixture_path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    coaching_path.write_text(
        json.dumps(
            {
                "bundle": bundle.to_dict(),
                "rotation_forecasts": rotation,
                "loo_diagnostic": loo,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "fixture_path": str(fixture_path),
        "coaching_path": str(coaching_path),
        "game": f"{meta['away_team_id']}@{meta['home_team_id']}",
        "status": meta["status"],
        "players": len(players),
        "substitutions": len(subs),
        "foul_events": len(fouls),
        "hot_cold": len(hot_cold),
        "source_url": doc.source_url,
        "fetched_at_utc": doc.fetched_at_utc,
        "loo_accuracy": loo.get("accuracy"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
