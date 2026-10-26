"""Synthetic observed player prop comparisons. No real bets or settlements."""
from dataclasses import replace
from datetime import datetime, timezone
import unittest

from research.props.prop_board import Game, PropQuote, SourceStamp
from research.props.observed_outcome import (
    ObservedPlayerStat, compare_observed_stat,
)


def t(hour, day=25):
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc)


H = "f" * 64


def sample(stat="22", side="over", line="20.5", sport="NBA"):
    gm = Game(sport, sport.lower() + ":fake-1",
              "team:home", "team:away", t(20))
    source = SourceStamp("synthetic", "https://example.org/quote",
                         t(13), t(14), H)
    q = PropQuote("quote:fake-1", gm.event_id, "athlete:one", "team:home",
                  "points" if sport == "NBA" else "receiving_yards",
                  "full_game", side, line, -110, "synthetic-book", source)
    final = ObservedPlayerStat(
        event_id=gm.event_id, athlete_id=q.athlete_id,
        team_id=q.team_id, market=q.market, period=q.period,
        participation="played", actual_stat=stat, game_final=True,
        source=SourceStamp("synthetic", "https://example.org/final",
                           t(22), t(23), H),
    )
    return gm, q, final, t(23, 26)


class ObservedOutcomeTests(unittest.TestCase):
    def test_over_is_mathematically_above_line(self):
        report = compare_observed_stat(*sample())
        self.assertTrue(report.structurally_valid, report.reasons)
        self.assertEqual(report.comparison, "selected_over")
        self.assertFalse(report.official_book_settlement_verified)
        self.assertFalse(report.scoring_eligible)

    def test_under_selection_above_line_is_miss(self):
        self.assertEqual(compare_observed_stat(*sample(side="under")).
                         comparison, "selected_under_lost")

    def test_under_selection_below_line_is_mathematical_win(self):
        self.assertEqual(compare_observed_stat(*sample(stat="19", side="under")).
                         comparison, "selected_under")

    def test_over_selection_below_line_is_miss(self):
        self.assertEqual(compare_observed_stat(*sample(stat="19")).
                         comparison, "selected_over_lost")

    def test_equal_line_is_push_not_win(self):
        self.assertEqual(compare_observed_stat(*sample(stat="20.5")).
                         comparison, "push")

    def test_dnp_does_not_assume_void_or_loss(self):
        gm, q, final, as_of = sample()
        final = replace(final, participation="dnp", actual_stat=None)
        report = compare_observed_stat(gm, q, final, as_of)
        self.assertTrue(report.structurally_valid, report.reasons)
        self.assertEqual(report.comparison, "dnp_needs_rules")
        self.assertFalse(report.official_book_settlement_verified)

    def test_unknown_player_result_remains_unresolved(self):
        gm, q, final, as_of = sample()
        final = replace(final, participation="unknown", actual_stat=None,
                        source=None)
        report = compare_observed_stat(gm, q, final, as_of)
        self.assertEqual(report.comparison, "unresolved")

    def test_unfinished_game_cannot_be_scored(self):
        gm, q, final, as_of = sample()
        final = replace(final, game_final=False)
        report = compare_observed_stat(gm, q, final, as_of)
        self.assertIn("game_not_confirmed_final", report.reasons)
        self.assertEqual(report.comparison, "invalid")

    def test_wrong_athlete_cannot_be_matched(self):
        gm, q, final, as_of = sample()
        final = replace(final, athlete_id="athlete:wrong")
        report = compare_observed_stat(gm, q, final, as_of)
        self.assertIn("athlete_team_identity_mismatch", report.reasons)
        self.assertEqual(report.comparison, "invalid")

    def test_wrong_team_cannot_be_matched(self):
        gm, q, final, as_of = sample()
        final = replace(final, team_id="team:away")
        self.assertIn("athlete_team_identity_mismatch",
                      compare_observed_stat(gm, q, final, as_of).reasons)

    def test_wrong_game_cannot_be_matched(self):
        gm, q, final, as_of = sample()
        final = replace(final, event_id="nba:other")
        self.assertIn("event_identity_mismatch",
                      compare_observed_stat(gm, q, final, as_of).reasons)

    def test_wrong_market_cannot_be_matched(self):
        gm, q, final, as_of = sample()
        final = replace(final, market="rebounds")
        self.assertIn("market_period_mismatch",
                      compare_observed_stat(gm, q, final, as_of).reasons)

    def test_final_source_after_cutoff_rejected(self):
        gm, q, final, _ = sample()
        report = compare_observed_stat(gm, q, final, t(22))
        self.assertIn("outcome_source_after_review", report.reasons)

    def test_final_source_before_event_rejected(self):
        gm, q, final, as_of = sample()
        final = replace(final, source=SourceStamp(
            "synthetic", "https://example.org/premature", t(16), t(17), H))
        self.assertIn("outcome_source_before_event_start",
                      compare_observed_stat(gm, q, final, as_of).reasons)

    def test_quote_after_tipoff_rejected(self):
        gm, q, final, as_of = sample()
        q = replace(q, source=SourceStamp(
            "synthetic", "https://example.org/late", t(21), t(22), H))
        self.assertIn("quote_not_known_before_event",
                      compare_observed_stat(gm, q, final, as_of).reasons)

    def test_as_of_not_postgame_rejected(self):
        gm, q, final, _ = sample()
        report = compare_observed_stat(gm, q, final, t(20))
        self.assertIn("outcome_review_before_event_start", report.reasons)

    def test_outcome_number_cannot_be_nan(self):
        gm, q, final, as_of = sample()
        with self.assertRaises(ValueError):
            replace(final, actual_stat="NaN")

    def test_dnp_cannot_claim_actual_stat(self):
        gm, q, final, as_of = sample()
        with self.assertRaises(ValueError):
            replace(final, participation="dnp")

    def test_game_final_must_be_bool(self):
        gm, q, final, as_of = sample()
        with self.assertRaises(ValueError):
            replace(final, game_final="final")

    def test_missing_final_receipt_rejected(self):
        gm, q, final, as_of = sample()
        with self.assertRaises(ValueError):
            replace(final, source=None)

    def test_original_line_not_changed_by_outcome(self):
        gm, q, final, as_of = sample()
        report = compare_observed_stat(gm, q, final, as_of)
        self.assertEqual(report.original_line, "20.5")
        self.assertEqual(q.line, "20.5")

    def test_other_sports_require_compatible_market(self):
        gm, q, final, as_of = sample(sport="NFL")
        self.assertEqual(compare_observed_stat(gm, q, final, as_of).
                         comparison, "selected_over")

    def test_sport_mismatched_stat_market_rejected(self):
        gm, q, final, as_of = sample(sport="NFL")
        q = replace(q, market="points")
        final = replace(final, market="points")
        report = compare_observed_stat(gm, q, final, as_of)
        self.assertIn("market_period_mismatch", report.reasons)


if __name__ == "__main__":
    unittest.main()
