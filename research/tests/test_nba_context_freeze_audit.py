"""Synthetic-only tests of banked-game chronology at projection freeze.

No NBA, sportsbook, official injury, or settlement claims are made.
"""
from dataclasses import replace
import unittest

from research.props.nba_context_audit import (
    BankedGameEvidence, OpponentDefenseEvidence, PlayerRoleEvidence,
    audit_nba_prop_context,
)
from research.props.nba_context_freeze_audit import audit_nba_frozen_bank
from research.props.prop_board import PropProjection, PropQuote, PropScreen, RosterAthlete
from research.tests.test_nba_context_audit import fixture, stamp, t


def audit(case):
    return audit_nba_frozen_bank(*case, season="2026-27")


def late_bank(case, *, final_hour=13, receipt_hour=14):
    """Replace one of five home-team games with a later completed game."""
    case[6] = (
        replace(case[6][0], event_id="nba:late-game",
                game_final_at=t(25, final_hour),
                source=stamp(25, receipt_hour)),
    ) + case[6][1:]
    return case


class NBAContextFreezeTests(unittest.TestCase):
    def test_baseline_fixture_has_five_games_for_both_teams_at_projection_inputs(self):
        result = audit(fixture())
        self.assertTrue(result.parent_context_complete, result.reasons)
        self.assertTrue(result.context_complete, result.reasons)
        self.assertEqual(result.expected_player_market_rows, 2)
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.rows[0].home_bank_games_at_inputs, 5)
        self.assertEqual(result.rows[0].away_bank_games_at_inputs, 5)
        self.assertTrue(result.rows[0].five_game_bank_at_inputs)
        self.assertIsNone(result.rows[1].five_game_bank_at_inputs)
        self.assertFalse(result.play_authorized)
        self.assertFalse(result.scoring_authorized)
        self.assertFalse(result.source_independently_verified)

    def test_reproduces_parent_hindsight_bank_gap(self):
        case = late_bank(fixture())
        # All five home games are complete by board review, but only four
        # were known when the model's input data was frozen.
        parent = audit_nba_prop_context(*case, season="2026-27")
        self.assertTrue(parent.context_complete, parent.reasons)
        result = audit(case)
        self.assertTrue(result.parent_context_complete)
        self.assertFalse(result.context_complete)
        self.assertEqual(result.rows[0].home_bank_games_at_inputs, 4)
        self.assertEqual(result.rows[0].away_bank_games_at_inputs, 5)
        self.assertIn("five_games_per_team_not_banked_at_projection_inputs",
                      result.rows[0].reasons)

    def test_source_capture_after_projection_inputs_does_not_count(self):
        case = fixture()
        case[6] = (
            replace(case[6][0], event_id="nba:early-final-late-source",
                    game_final_at=t(25, 10), source=stamp(25, 13)),
        ) + case[6][1:]
        self.assertTrue(audit_nba_prop_context(*case, season="2026-27").context_complete)
        self.assertEqual(audit(case).rows[0].home_bank_games_at_inputs, 4)

    def test_source_published_after_projection_inputs_does_not_count(self):
        case = fixture()
        case[6] = (
            replace(case[6][0], event_id="nba:published-late",
                    game_final_at=t(25, 10), source=stamp(25, 13)),
        ) + case[6][1:]
        self.assertFalse(audit(case).context_complete)

    def test_game_final_at_exact_inputs_time_can_count_if_receipt_known(self):
        case = fixture()
        case[6] = (
            replace(case[6][0], event_id="nba:just-in-time",
                    game_final_at=t(25, 12), source=stamp(25, 12)),
        ) + case[6][1:]
        self.assertTrue(audit(case).context_complete)

    def test_projection_inputs_moved_after_bank_receipt_restores_context(self):
        case = late_bank(fixture())
        # A model frozen at 13:00 cannot claim 14:00 inputs.
        with self.assertRaises(ValueError):
            replace(case[4][0], inputs_as_of=t(25, 14))

    def test_legitimate_later_projection_freeze_can_use_later_bank(self):
        case = late_bank(fixture())
        case[4] = (replace(case[4][0], frozen_at=t(25, 14, 30),
                           inputs_as_of=t(25, 14)),)
        # The original quote was captured at 14:00; this cannot become
        # an independently projected-before-market quote.
        result = audit(case)
        self.assertTrue(result.rows[0].five_game_bank_at_inputs)
        self.assertFalse(result.context_complete)
        self.assertIn("market_quoted_before_independent_projection:quote:one",
                      result.reasons)

    def test_six_games_with_one_late_still_meets_five_early(self):
        case = fixture()
        case[6] = case[6] + (
            BankedGameEvidence("nba:late-extra", "team:home", "2026-27",
                               t(25, 13), stamp(25, 14)),
        )
        result = audit(case)
        self.assertTrue(result.context_complete, result.reasons)
        self.assertEqual(result.rows[0].home_bank_games_at_inputs, 5)

    def test_duplicate_early_game_cannot_fill_bank(self):
        case = fixture()
        case[6] = case[6] + (case[6][0],)
        result = audit(case)
        self.assertEqual(result.rows[0].home_bank_games_at_inputs, 4)
        self.assertFalse(result.context_complete)

    def test_wrong_season_game_cannot_fill_bank(self):
        case = fixture()
        case[6] = (replace(case[6][0], season="2025-26"),) + case[6][1:]
        self.assertEqual(audit(case).rows[0].home_bank_games_at_inputs, 4)

    def test_current_event_cannot_fill_bank(self):
        case = fixture()
        case[6] = (replace(case[6][0], event_id=case[0].event_id),) + case[6][1:]
        self.assertEqual(audit(case).rows[0].home_bank_games_at_inputs, 4)

    def test_invalid_receipt_cannot_fill_bank(self):
        case = fixture()
        case[6] = (
            replace(case[6][0], source=stamp(18, 19)),
        ) + case[6][1:]
        self.assertEqual(audit(case).rows[0].home_bank_games_at_inputs, 4)

    def test_earlier_projection_cannot_borrow_later_banked_games(self):
        case = late_bank(fixture())
        case[4] = (replace(case[4][0], frozen_at=t(25, 11),
                           inputs_as_of=t(25, 10)),)
        result = audit(case)
        self.assertEqual(result.rows[0].home_bank_games_at_inputs, 4)
        self.assertFalse(result.context_complete)

    def test_missing_projection_does_not_silently_select_another(self):
        case = fixture()
        case[4] = ()
        result = audit(case)
        self.assertIn("missing_or_ambiguous_frozen_projection", result.rows[0].reasons)
        self.assertFalse(result.context_complete)

    def test_duplicate_projection_is_ambiguous_not_last_wins(self):
        case = fixture()
        case[4] = case[4] + (replace(case[4][0], artifact_sha256="c" * 64),)
        result = audit(case)
        self.assertIn("missing_or_ambiguous_frozen_projection", result.rows[0].reasons)
        self.assertFalse(result.context_complete)

    def test_wrong_team_projection_cannot_satisfy_player(self):
        case = fixture()
        case[4] = (replace(case[4][0], team_id="team:away"),)
        self.assertIn("projection_team_identity_mismatch", audit(case).rows[0].reasons)

    def test_unresolved_bench_player_stays_in_denominator(self):
        case = fixture()
        case[1] = case[1] + (
            RosterAthlete("athlete:bench", "team:home", "active", stamp(25, 9)),)
        result = audit(case)
        self.assertEqual(result.expected_player_market_rows, 3)
        self.assertEqual(len(result.rows), 3)
        self.assertEqual(result.rows[2].decision, "missing")
        self.assertFalse(result.context_complete)

    def test_excluded_player_needs_no_projection_bank(self):
        case = fixture()
        case[3] = (replace(case[3][0], decision="exclude", reason="role"),
                   case[3][1])
        case[4], case[5] = (), ()
        result = audit(case)
        self.assertTrue(result.context_complete, result.reasons)
        self.assertIsNone(result.rows[0].five_game_bank_at_inputs)

    def test_zero_candidates_never_creates_a_play(self):
        case = fixture()
        case[3] = (replace(case[3][0], decision="exclude", reason="no role"),
                   case[3][1])
        case[4], case[5] = (), ()
        result = audit(case)
        self.assertFalse(result.play_authorized)
        self.assertFalse(result.scoring_authorized)

    def test_two_player_projections_have_independent_bank_cutoffs(self):
        case = fixture()
        case[1] = (case[1][0], replace(case[1][1], availability="active"))
        case[3] = (case[3][0], replace(case[3][1], decision="consider",
                                      reason="active"))
        case[4] = case[4] + (
            PropProjection("athlete:two", "team:away", "points", "18.0",
                           t(25, 13), t(25, 10), "d" * 64),)
        case[5] = case[5] + (
            PropQuote("quote:two", case[0].event_id, "athlete:two",
                      "team:away", "points", "full_game", "under",
                      "20.5", -110, "synthetic-book", stamp(25, 14)),)
        case[7] = case[7] + (
            PlayerRoleEvidence("athlete:two", "team:away", "available",
                               "official_report", stamp(25, 9), "28",
                               "rotation", stamp(25, 9)),)
        case[8] = case[8] + (
            OpponentDefenseEvidence("team:home", "points", "full_game", 8,
                                    "20", "standalone synthetic allowance",
                                    True, stamp(24, 10, digest="e" * 64)),)
        # A banked home game becomes known at 11:00, before athlete one's
        # 12:00 input cutoff but after athlete two's 10:00 input cutoff.
        case[6] = (
            replace(case[6][0], event_id="nba:late-for-second",
                    game_final_at=t(25, 11), source=stamp(25, 11)),
        ) + case[6][1:]
        parent = audit_nba_prop_context(*case, season="2026-27")
        self.assertTrue(parent.context_complete, parent.reasons)
        result = audit(case)
        self.assertTrue(result.rows[0].five_game_bank_at_inputs)
        self.assertFalse(result.rows[1].five_game_bank_at_inputs)
        self.assertEqual(result.rows[0].home_bank_games_at_inputs, 5)
        self.assertEqual(result.rows[1].home_bank_games_at_inputs, 4)
        self.assertFalse(result.context_complete)

    def test_parent_failure_still_blocks_even_with_early_bank(self):
        case = fixture()
        case[7] = ()
        result = audit(case)
        self.assertTrue(result.projection_bank_complete)
        self.assertFalse(result.parent_context_complete)
        self.assertFalse(result.context_complete)

    def test_unverified_receipts_never_become_source_verified(self):
        result = audit(fixture())
        self.assertFalse(result.source_independently_verified)
        self.assertFalse(result.scoring_authorized)
        self.assertFalse(result.play_authorized)


if __name__ == "__main__":
    unittest.main()
