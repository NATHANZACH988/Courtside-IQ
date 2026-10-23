"""Foul trouble research tests."""

from __future__ import annotations

import unittest

from research.foul_trouble import FoulRateSample, apply_foul_penalty, assess_foul_trouble


class FoulTroubleTests(unittest.TestCase):
    def test_elevated_pf_reduces_minutes(self):
        samples = [
            FoulRateSample("g1", minutes=30, personal_fouls=5, period_fouls=(2, 1, 1, 1)),
            FoulRateSample("g2", minutes=28, personal_fouls=6, period_fouls=(3, 1, 1, 1)),
            FoulRateSample("g3", minutes=32, personal_fouls=4, period_fouls=(2, 1, 0, 1)),
        ]
        assessment = assess_foul_trouble(samples)
        self.assertGreater(assessment.fouls_per_36, 3.0)
        self.assertGreater(assessment.projected_minutes_penalty, 0)
        projected = apply_foul_penalty(34.0, assessment)
        self.assertLess(projected, 34.0)

    def test_empty_samples_assumed(self):
        a = assess_foul_trouble([])
        self.assertEqual(a.verification, "assumed")
        self.assertEqual(apply_foul_penalty(30, a), 30.0)


if __name__ == "__main__":
    unittest.main()
