"""Unit tests for closeness-v1 scoring."""

from __future__ import annotations

import unittest

from arena.scoring import (
    SCORING_VERSION,
    UnsupportedStatError,
    closeness_score,
    grade_prediction,
    is_provisional,
)


class ScoringTests(unittest.TestCase):
    def test_exact_is_100(self):
        self.assertEqual(closeness_score(25, 25, "PTS"), 100.0)

    def test_points_vs_rebounds_scale(self):
        # Off by 3 points should score higher than off by 3 rebounds
        pts = closeness_score(25, 28, "PTS")
        reb = closeness_score(8, 11, "REB")
        self.assertGreater(pts, reb)
        self.assertEqual(pts, 75.0)  # 100 * (1 - 3/12)
        self.assertEqual(reb, 50.0)  # 100 * (1 - 3/6)

    def test_floor_at_zero(self):
        self.assertEqual(closeness_score(0, 40, "PTS"), 0.0)

    def test_unsupported_stat(self):
        with self.assertRaises(UnsupportedStatError):
            closeness_score(1, 1, "FANTASY")

    def test_grade_includes_skill_delta(self):
        g = grade_prediction(predicted=24, actual=26, baseline=20, stat="PTS")
        self.assertEqual(g.scoring_version, SCORING_VERSION)
        self.assertEqual(g.score, closeness_score(24, 26, "PTS"))
        self.assertEqual(g.baseline_score, closeness_score(20, 26, "PTS"))
        self.assertEqual(g.skill_delta, round(g.score - g.baseline_score, 2))

    def test_provisional_threshold(self):
        self.assertTrue(is_provisional(4))
        self.assertFalse(is_provisional(5))

    def test_deterministic(self):
        a = closeness_score(10.5, 12, "AST")
        b = closeness_score(10.5, 12, "AST")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
