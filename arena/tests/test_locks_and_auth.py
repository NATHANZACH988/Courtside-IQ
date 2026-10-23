"""Reliability: locks, commissioner auth, voids, cross-league forecast denial."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arena.db import Database
from arena.errors import ForbiddenError, LockPassedError, ValidationError
from arena.service import ArenaService


class LocksAndAuthTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2024, 1, 14, 20, 0, 0, tzinfo=timezone.utc)
        self.svc = ArenaService(Database(":memory:"), clock=lambda: self.now)

    def _slate(self, owner, tip="2024-01-15T00:30:00Z"):
        league = self.svc.create_league(owner, "Auth League")
        slate = self.svc.create_slate(
            owner,
            league["id"],
            date_utc="2024-01-15",
            questions=[
                {
                    "game": {
                        "id": "g-auth",
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
        return league, slate

    def test_non_commissioner_cannot_void(self):
        owner = self.svc.create_user("Owner")
        member = self.svc.create_user("Member")
        league, slate = self._slate(owner)
        self.svc.join_league(member, league["invite_code"])
        qid = slate["questions"][0]["id"]
        with self.assertRaises(ForbiddenError):
            self.svc.void_question(member, qid, reason="nope")

    def test_void_requires_reason(self):
        owner = self.svc.create_user("Owner2")
        _, slate = self._slate(owner)
        with self.assertRaises(ValidationError):
            self.svc.void_question(owner, slate["questions"][0]["id"], reason="  ")

    def test_outsider_cannot_forecast(self):
        owner = self.svc.create_user("Owner3")
        outsider = self.svc.create_user("Outsider")
        _, slate = self._slate(owner)
        with self.assertRaises(ForbiddenError):
            self.svc.submit_forecast(outsider, slate["questions"][0]["id"], 20)

    def test_duplicate_submit_keeps_history(self):
        owner = self.svc.create_user("Owner4")
        _, slate = self._slate(owner)
        qid = slate["questions"][0]["id"]
        e1 = self.svc.submit_forecast(owner, qid, 20)
        e2 = self.svc.submit_forecast(owner, qid, 22)
        self.assertNotEqual(e1["id"], e2["id"])
        self.assertEqual(e2["prior_event_id"], e1["id"])
        latest = self.svc._latest_forecast(qid, owner["id"])
        self.assertEqual(latest["predicted_value"], 22)

    def test_lock_at_exact_tipoff(self):
        owner = self.svc.create_user("Owner5")
        tip = "2024-01-14T21:00:00Z"  # future at slate creation
        _, slate = self._slate(owner, tip=tip)
        self.now = datetime(2024, 1, 14, 21, 0, 0, tzinfo=timezone.utc)
        with self.assertRaises(LockPassedError):
            self.svc.submit_forecast(owner, slate["questions"][0]["id"], 21)


if __name__ == "__main__":
    unittest.main()
