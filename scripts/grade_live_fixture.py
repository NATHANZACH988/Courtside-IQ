#!/usr/bin/env python3
"""Run prediction→grading vertical slice against a live-captured fixture.

Demonstrates Priority-tonight milestone with real completed-game box scores.
Predictions are illustrative (house AI = baseline; sample humans nearby).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arena.db import Database
from arena.service import ArenaService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture",
        default=str(
            ROOT / "fixtures" / "box_scores" / "live_captures" / "401909848.json"
        ),
    )
    args = parser.parse_args()
    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    if not fixture.get("source_url") or not fixture.get("fetched_at_utc"):
        raise SystemExit("Fixture missing provenance")

    tip = datetime.fromisoformat(fixture["scheduled_tipoff_utc"].replace("Z", "+00:00"))
    # Clock starts before tip so submissions are legal, then advances past tip.
    pre_tip = tip - timedelta(hours=2)

    class Clock:
        def __init__(self):
            self.now = pre_tip

        def __call__(self):
            return self.now

    clock = Clock()
    svc = ArenaService(Database(":memory:"), clock=clock)

    commissioner = svc.create_user("Live Commissioner")
    alice = svc.create_user("Live Alice")
    league = svc.create_league(commissioner, "Tonight Live Grade")
    svc.join_league(alice, league["invite_code"])

    # Pick top two scorers by minutes*usage proxy for the slate questions
    ranked = sorted(fixture["players"], key=lambda p: (p["PTS"], p["minutes"]), reverse=True)
    q_specs = []
    for p, stat in ((ranked[0], "PTS"), (ranked[1], "REB")):
        baseline = float(p[stat])  # freeze "season avg" stand-in from this box for demo
        # For a fair skill demo, freeze a slightly off baseline
        frozen = max(0.0, baseline - 2.0)
        q_specs.append(
            {
                "game": {
                    "id": fixture["game_id"],
                    "season": fixture.get("season") or "2026-27",
                    "home_team_id": fixture["home_team_id"],
                    "away_team_id": fixture["away_team_id"],
                    "scheduled_tipoff_utc": fixture["scheduled_tipoff_utc"],
                    "status": "final",
                },
                "player": {
                    "id": p["player_id"],
                    "full_name": p["full_name"],
                    "team_id": p["team_id"],
                },
                "stat": stat,
                "frozen_baseline": frozen,
                "prompt_text": f"How many {stat} will {p['full_name']} finish with?",
                "actual": float(p[stat]),
            }
        )

    slate = svc.create_slate(
        commissioner,
        league["id"],
        date_utc=fixture["scheduled_tipoff_utc"][:10],
        questions=[{k: v for k, v in q.items() if k != "actual"} for q in q_specs],
    )

    # Human predictions (closer on first, farther on second)
    for q, spec in zip(slate["questions"], q_specs):
        guess = spec["actual"] if q["stat"] == "PTS" else spec["actual"] + 3
        svc.submit_forecast(alice, q["id"], guess)

    clock.now = tip + timedelta(minutes=1)
    svc.lock_due_questions()

    for q, spec in zip(slate["questions"], q_specs):
        # refresh question ids order by matching player/stat
        pass

    # Map by player_id+stat
    by_key = {(s["player"]["id"], s["stat"]): s for s in q_specs}
    for q in slate["questions"]:
        spec = by_key[(q["player_id"], q["stat"])]
        svc.ingest_result(
            commissioner,
            q["id"],
            actual_value=spec["actual"],
            source_url=fixture["source_url"],
            fetched_at_utc=fixture["fetched_at_utc"],
            fixture_id=fixture["fixture_id"],
        )

    graded = svc.grade_slate(commissioner, slate["id"])
    print(
        json.dumps(
            {
                "fixture_id": fixture["fixture_id"],
                "source_url": fixture["source_url"],
                "fetched_at_utc": fixture["fetched_at_utc"],
                "game": f"{fixture['away_team_id']}@{fixture['home_team_id']}",
                "score": f"{fixture.get('away_score')}-{fixture.get('home_score')}",
                "questions": [
                    {
                        "prompt": q["prompt_text"],
                        "stat": q["stat"],
                        "baseline": q["frozen_baseline"],
                        "actual": by_key[(q["player_id"], q["stat"])]["actual"],
                    }
                    for q in slate["questions"]
                ],
                "leaderboard": graded["leaderboard"],
                "grade_count": len(graded["grades"]),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
