"""End-to-end: slate → baseline → predict → lock → result → grade → leaderboard → audit."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arena.db import Database
from arena.errors import ForbiddenError, LockPassedError
from arena.service import ArenaService
from scripts.load_fixture import load_box_score, player_stat


class VerticalSliceTests(unittest.TestCase):
    def setUp(self):
        self.fixed_now = datetime(2024, 1, 14, 18, 0, 0, tzinfo=timezone.utc)
        self.db = Database(":memory:")
        self.svc = ArenaService(self.db, clock=lambda: self.fixed_now)
        self.fixture = load_box_score()

    def _advance(self, **delta):
        self.fixed_now = self.fixed_now + timedelta(**delta)

    def test_full_workflow_with_attributed_fixture(self):
        commissioner = self.svc.create_user("Commissioner Nate")
        alice = self.svc.create_user("Alice")
        bob = self.svc.create_user("Bob")

        league = self.svc.create_league(commissioner, "Beta League")
        self.svc.join_league(alice, league["invite_code"])
        self.svc.join_league(bob, league["invite_code"])

        tip = self.fixture["scheduled_tipoff_utc"]
        game = {
            "id": self.fixture["game_id"],
            "season": self.fixture["season"],
            "home_team_id": self.fixture["home_team_id"],
            "away_team_id": self.fixture["away_team_id"],
            "scheduled_tipoff_utc": tip,
            "status": "scheduled",
        }
        tatum = next(p for p in self.fixture["players"] if p["player_id"] == "ply_tatum")
        hali = next(p for p in self.fixture["players"] if p["player_id"] == "ply_haliburton")

        slate = self.svc.create_slate(
            commissioner,
            league["id"],
            date_utc="2024-01-15",
            questions=[
                {
                    "game": game,
                    "player": {
                        "id": tatum["player_id"],
                        "full_name": tatum["full_name"],
                        "team_id": tatum["team_id"],
                        "position": tatum["position"],
                    },
                    "stat": "PTS",
                    "frozen_baseline": 27.0,
                    "prompt_text": "How many points will Jayson Tatum score?",
                    "scheduled_tipoff_utc": tip,
                },
                {
                    "game": game,
                    "player": {
                        "id": hali["player_id"],
                        "full_name": hali["full_name"],
                        "team_id": hali["team_id"],
                        "position": hali["position"],
                    },
                    "stat": "AST",
                    "frozen_baseline": 10.0,
                    "prompt_text": "How many assists will Tyrese Haliburton finish with?",
                    "scheduled_tipoff_utc": tip,
                },
            ],
        )
        self.assertEqual(slate["scoring_version"], "closeness-v1")
        q_pts = next(q for q in slate["questions"] if q["stat"] == "PTS")
        q_ast = next(q for q in slate["questions"] if q["stat"] == "AST")
        self.assertEqual(q_pts["frozen_baseline"], 27.0)
        self.assertEqual(q_ast["frozen_baseline"], 10.0)

        # House AI is auto-seeded at slate creation with frozen baselines.
        # Humans submit before tipoff under the same lock rules.
        self.svc.submit_forecast(alice, q_pts["id"], 26)
        self.svc.submit_forecast(alice, q_ast["id"], 12)
        self.svc.submit_forecast(bob, q_pts["id"], 30)
        self.svc.submit_forecast(bob, q_ast["id"], 9)

        # Competitors hidden before lock
        pre = self.svc.get_slate(slate["id"], viewer=alice)
        pre_pts = next(q for q in pre["questions"] if q["stat"] == "PTS")
        self.assertIsNone(pre_pts["forecasts"])
        self.assertEqual(pre_pts["my_prediction"]["predicted_value"], 26)

        # Late submission rejected (server-side)
        self._advance(hours=8)  # past tipoff 00:30Z on Jan 15 from Jan 14 18:00
        with self.assertRaises(LockPassedError):
            self.svc.submit_forecast(alice, q_pts["id"], 99)

        locked = self.svc.lock_due_questions()
        self.assertGreaterEqual(locked, 2)

        # After lock, forecasts visible
        post = self.svc.get_slate(slate["id"], viewer=alice)
        post_pts = next(q for q in post["questions"] if q["stat"] == "PTS")
        self.assertIsNotNone(post_pts["forecasts"])
        self.assertTrue(post_pts["is_locked"])

        # Ingest attributed results from offline fixture
        for q, pid, stat in (
            (q_pts, "ply_tatum", "PTS"),
            (q_ast, "ply_haliburton", "AST"),
        ):
            self.svc.ingest_result(
                commissioner,
                q["id"],
                actual_value=player_stat(self.fixture, pid, stat),
                source_url=self.fixture["source_url"],
                fetched_at_utc=self.fixture["fetched_at_utc"],
                source_updated_at_utc=self.fixture.get("source_updated_at_utc"),
                fixture_id=self.fixture["fixture_id"],
            )

        graded = self.svc.grade_slate(commissioner, slate["id"])
        self.assertGreaterEqual(len(graded["grades"]), 6)
        board = graded["leaderboard"]
        self.assertEqual(board["scoring_basis"], "mean_accuracy")
        self.assertTrue(any(e["is_house_ai"] for e in board["entries"]))
        # Low sample → provisional
        self.assertTrue(all(e["provisional"] for e in board["entries"]))

        # Alice predicted 26 PTS (actual 26) and 12 AST (actual 11) — should beat Bob
        alice_entry = next(e for e in board["entries"] if e["display_name"] == "Alice")
        bob_entry = next(e for e in board["entries"] if e["display_name"] == "Bob")
        self.assertGreater(alice_entry["mean_accuracy"], bob_entry["mean_accuracy"])
        self.assertEqual(alice_entry["rank"], 1)

        audit = self.svc.audit_for_question(alice, q_pts["id"])
        self.assertGreaterEqual(len(audit["forecast_events"]), 3)
        self.assertTrue(
            any(a["action"] == "result_ingested" for a in audit["audit_log"])
        )

        # Commissioner correction creates new event, does not mutate original
        original_events = len(audit["forecast_events"])
        self.svc.correct_forecast(
            commissioner, q_pts["id"], bob["id"], 26, reason="Wrong player entered"
        )
        audit2 = self.svc.audit_for_question(alice, q_pts["id"])
        self.assertEqual(len(audit2["forecast_events"]), original_events + 1)
        # Originals preserved — correction is append-only
        types = [e["event_type"] for e in audit2["forecast_events"]]
        self.assertIn("submit", types)
        self.assertIn("correction", types)
        original_ids = {e["id"] for e in audit["forecast_events"]}
        self.assertTrue(original_ids.issubset({e["id"] for e in audit2["forecast_events"]}))

    def test_cross_league_isolation(self):
        a = self.svc.create_user("A")
        b = self.svc.create_user("B")
        la = self.svc.create_league(a, "League A")
        lb = self.svc.create_league(b, "League B")
        with self.assertRaises(ForbiddenError):
            self.svc.get_league(la["id"], viewer=b)
        with self.assertRaises(ForbiddenError):
            self.svc.get_league(lb["id"], viewer=a)

    def test_idempotent_submit(self):
        u = self.svc.create_user("Idem")
        league = self.svc.create_league(u, "Idem League")
        tip = "2024-01-15T00:30:00Z"
        slate = self.svc.create_slate(
            u,
            league["id"],
            date_utc="2024-01-15",
            questions=[
                {
                    "game": {
                        "id": "g1",
                        "season": "2023-24",
                        "home_team_id": "BOS",
                        "away_team_id": "IND",
                        "scheduled_tipoff_utc": tip,
                    },
                    "player": {
                        "id": "ply_tatum",
                        "full_name": "Jayson Tatum",
                        "team_id": "BOS",
                    },
                    "stat": "PTS",
                    "frozen_baseline": 27,
                    "prompt_text": "PTS?",
                }
            ],
        )
        qid = slate["questions"][0]["id"]
        e1 = self.svc.submit_forecast(u, qid, 25, client_request_id="req-1")
        e2 = self.svc.submit_forecast(u, qid, 99, client_request_id="req-1")
        self.assertEqual(e1["id"], e2["id"])
        self.assertEqual(e2["predicted_value"], 25)


if __name__ == "__main__":
    unittest.main()
