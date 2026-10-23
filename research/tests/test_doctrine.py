"""Doctrine gate tests."""

from __future__ import annotations

import unittest

from research.doctrine import Verdict, decide_verdict


class DoctrineTests(unittest.TestCase):
    def test_play_blocked_without_five_games(self):
        d = decide_verdict(3, opportunity_rank_ok=True, evidence_strength=0.9)
        self.assertEqual(d.verdict, Verdict.PASS)

    def test_owner_override_allows_play(self):
        d = decide_verdict(
            3, opportunity_rank_ok=True, evidence_strength=0.9, owner_override=True
        )
        self.assertEqual(d.verdict, Verdict.PLAY)

    def test_lean_band(self):
        d = decide_verdict(8, opportunity_rank_ok=True, evidence_strength=0.6)
        self.assertEqual(d.verdict, Verdict.LEAN)


if __name__ == "__main__":
    unittest.main()
