"""Hot/cold streak research tests."""

from __future__ import annotations

import unittest

from research.streaks import (
    StatGame,
    apply_streak_to_projection,
    apply_teammate_spillover,
    assess_streak,
)


class StreakTests(unittest.TestCase):
    def test_hot_streak_raises_self_and_crowds_teammates(self):
        # Flat season then surge
        games = [StatGame(f"g{i}", value=15, minutes=30) for i in range(10)]
        games += [StatGame(f"h{i}", value=30, minutes=34) for i in range(5)]
        a = assess_streak(games, window=5)
        self.assertEqual(a.label, "hot")
        self.assertGreater(a.self_adjustment, 0)
        self.assertLess(a.teammate_spillover, 0)
        self.assertGreater(apply_streak_to_projection(20, a), 20)
        self.assertLess(apply_teammate_spillover(15, a), 15)

    def test_cold_streak_frees_teammates(self):
        games = [StatGame(f"g{i}", value=20, minutes=32) for i in range(10)]
        games += [StatGame(f"c{i}", value=8, minutes=28) for i in range(5)]
        a = assess_streak(games, window=5)
        self.assertEqual(a.label, "cold")
        self.assertLess(a.self_adjustment, 0)
        self.assertGreater(a.teammate_spillover, 0)

    def test_insufficient_games(self):
        a = assess_streak([StatGame("g1", 10, 20)])
        self.assertEqual(a.label, "neutral")
        self.assertEqual(a.verification, "assumed")


if __name__ == "__main__":
    unittest.main()
