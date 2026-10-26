"""Synthetic chronology regressions; never uses actual NBA or book data."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
import unittest

from research.props.final_chronology_audit import (
    EventFinalReceipt, audit_prop_outcome_final,
)
from research.props.observed_outcome import ObservedPlayerStat
from research.props.prop_board import Game, PropQuote, SourceStamp


def t(hour, minute=0):
    return datetime(2026, 10, 25, hour, minute, tzinfo=timezone.utc)


HASH = "b" * 64


def src(published, captured):
    return SourceStamp("synthetic", "https://example.org/raw",
                       published, captured, HASH)


def fixtures(sport="NBA"):
    game = Game(sport, sport.lower() + ":event1", "team:home",
                "team:away", t(20))
    market = "points" if sport == "NBA" else "receiving_yards"
    quote = PropQuote("quote:one", game.event_id, "athlete:one", "team:home",
                      market, "full_game", "over", "20.5", -110,
                      "synthetic-book", src(t(18), t(18, 10)))
    stat = ObservedPlayerStat(
        game.event_id, "athlete:one", "team:home", market, "full_game",
        "played", "22", True, src(t(22, 10), t(22, 15)),
    )
    final = EventFinalReceipt(game.event_id, "team:home", "team:away",
                              t(22), src(t(22), t(22, 5)))
    return game, quote, stat, final, t(23)


def run(case):
    return audit_prop_outcome_final(*case)


class PropFinalChronologyTests(unittest.TestCase):
    def test_valid_mathematical_comparison_but_not_settlement(self):
        result = run(fixtures())
        self.assertTrue(result.structurally_valid, result.reasons)
        self.assertEqual(result.comparison, "selected_over")
        self.assertEqual(result.actual_stat, "22")
        self.assertFalse(result.scoring_eligible)
        self.assertFalse(result.official_book_settlement_verified)
        self.assertFalse(result.source_independently_verified)

    def test_missing_final_receipt_blocks_even_when_game_final_flag_true(self):
        case = list(fixtures())
        case[3] = None
        result = run(case)
        self.assertEqual(result.comparison, "invalid")
        self.assertIn("event_final_receipt_missing", result.reasons)
        self.assertIsNone(result.actual_stat)

    def test_early_player_stat_published_before_game_final_is_blocked(self):
        case = list(fixtures())
        case[2] = replace(case[2], source=src(t(20, 5), t(20, 6)))
        result = run(case)
        self.assertIn("player_stat_published_before_event_final", result.reasons)
        self.assertIn("player_stat_captured_before_event_final", result.reasons)
        self.assertEqual(result.comparison, "invalid")
        self.assertIsNone(result.actual_stat)

    def test_early_player_stat_published_before_final_even_if_captured_after(self):
        case = list(fixtures())
        case[2] = replace(case[2], source=src(t(21, 59), t(22, 20)))
        result = run(case)
        self.assertIn("player_stat_published_before_event_final", result.reasons)
        self.assertNotIn("player_stat_captured_before_event_final", result.reasons)

    def test_early_event_final_source_published_before_final_is_blocked(self):
        case = list(fixtures())
        case[3] = replace(case[3], source=src(t(21), t(22, 5)))
        self.assertIn("event_final_published_before_final", run(case).reasons)

    def test_early_event_final_source_captured_before_final_is_blocked(self):
        case = list(fixtures())
        case[3] = replace(case[3], source=src(t(21), t(21, 30)))
        result = run(case)
        self.assertIn("event_final_captured_before_final", result.reasons)

    def test_final_claim_before_start_is_invalid(self):
        case = list(fixtures())
        case[3] = replace(case[3], final_at=t(19))
        self.assertIn("event_final_not_after_start", run(case).reasons)

    def test_future_final_time_cannot_be_used_at_cutoff(self):
        case = list(fixtures())
        case[3] = replace(case[3], final_at=t(23, 1))
        result = run(case)
        self.assertIn("event_final_after_review_cutoff", result.reasons)

    def test_event_final_source_not_known_at_cutoff(self):
        case = list(fixtures())
        case[3] = replace(case[3], source=src(t(22), t(23, 30)))
        self.assertIn("event_final_source_after_review_cutoff", run(case).reasons)

    def test_outcome_source_not_known_at_cutoff(self):
        case = list(fixtures())
        case[2] = replace(case[2], source=src(t(22, 10), t(23, 30)))
        self.assertIn("outcome_source_after_review", run(case).reasons)

    def test_event_id_mismatch_is_invalid(self):
        case = list(fixtures())
        case[3] = replace(case[3], event_id="nba:other")
        self.assertIn("event_final_identity_mismatch", run(case).reasons)

    def test_home_team_mismatch_is_invalid(self):
        case = list(fixtures())
        case[3] = replace(case[3], home_team_id="team:other")
        self.assertIn("event_final_identity_mismatch", run(case).reasons)

    def test_away_team_mismatch_is_invalid(self):
        case = list(fixtures())
        case[3] = replace(case[3], away_team_id="team:other")
        self.assertIn("event_final_identity_mismatch", run(case).reasons)

    def test_wrong_athlete_is_blocked_by_underlying_identity_audit(self):
        case = list(fixtures())
        case[2] = replace(case[2], athlete_id="athlete:other")
        self.assertIn("athlete_team_identity_mismatch", run(case).reasons)

    def test_wrong_player_team_is_blocked(self):
        case = list(fixtures())
        case[2] = replace(case[2], team_id="team:away")
        self.assertIn("athlete_team_identity_mismatch", run(case).reasons)

    def test_wrong_stat_market_is_blocked(self):
        case = list(fixtures())
        case[2] = replace(case[2], market="rebounds")
        self.assertIn("market_period_mismatch", run(case).reasons)

    def test_early_quote_is_allowed(self):
        result = run(fixtures())
        self.assertNotIn("quote_not_known_before_event", result.reasons)

    def test_posttip_quote_is_not_allowed(self):
        case = list(fixtures())
        case[1] = replace(case[1], source=src(t(21), t(21, 10)))
        self.assertIn("quote_not_known_before_event", run(case).reasons)

    def test_unfinished_game_cannot_be_declared_valid(self):
        case = list(fixtures())
        case[2] = replace(case[2], game_final=False)
        self.assertIn("game_not_confirmed_final", run(case).reasons)

    def test_dnp_requires_book_rules_even_after_final(self):
        case = list(fixtures())
        case[2] = replace(case[2], participation="dnp", actual_stat=None)
        result = run(case)
        self.assertTrue(result.structurally_valid)
        self.assertEqual(result.comparison, "dnp_needs_rules")
        self.assertFalse(result.official_book_settlement_verified)

    def test_unknown_participation_stays_unresolved(self):
        case = list(fixtures())
        case[2] = replace(case[2], participation="unknown", actual_stat=None,
                          source=None)
        result = run(case)
        self.assertTrue(result.structurally_valid, result.reasons)
        self.assertEqual(result.comparison, "unresolved")

    def test_equal_original_line_stays_push_not_win(self):
        case = list(fixtures())
        case[2] = replace(case[2], actual_stat="20.5")
        self.assertEqual(run(case).comparison, "push")

    def test_under_original_line_mathematical_miss(self):
        case = list(fixtures())
        case[1] = replace(case[1], side="under")
        self.assertEqual(run(case).comparison, "selected_under_lost")

    def test_nfl_receiving_yards_uses_same_final_gate(self):
        result = run(fixtures("NFL"))
        self.assertTrue(result.structurally_valid)
        self.assertEqual(result.market, "receiving_yards")

    def test_fake_source_receipt_rejected_at_creation(self):
        case = list(fixtures())
        with self.assertRaises(ValueError):
            replace(case[3], source={"captured_at": t(22)})

    def test_unsupported_final_status_rejected(self):
        case = list(fixtures())
        with self.assertRaises(ValueError):
            replace(case[3], status="in_progress")

    def test_naive_final_time_rejected(self):
        case = list(fixtures())
        with self.assertRaises(ValueError):
            replace(case[3], final_at=datetime(2026, 10, 25, 22))

    def test_final_evidence_is_immutable(self):
        case = list(fixtures())
        with self.assertRaises(FrozenInstanceError):
            case[3].final_at = t(21)

    def test_invalid_final_receipt_type_rejected(self):
        case = list(fixtures())
        case[3] = {"event_id": case[0].event_id}
        with self.assertRaises(TypeError):
            run(case)

    def test_invalid_as_of_time_rejected(self):
        case = list(fixtures())
        case[4] = datetime(2026, 10, 25, 23)
        with self.assertRaises(ValueError):
            run(case)


if __name__ == "__main__":
    unittest.main()
