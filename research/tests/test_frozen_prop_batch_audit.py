"""Synthetic frozen player-prop denominator tests; no sportsbook data."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
import unittest

from research.props.frozen_batch_audit import (
    FrozenPropSelection, audit_frozen_prop_batch,
)
from research.props.final_chronology_audit import EventFinalReceipt
from research.props.observed_outcome import ObservedPlayerStat
from research.props.prop_board import Game, PropQuote, SourceStamp


H = "c" * 64


def t(hour, minute=0):
    return datetime(2026, 10, 25, hour, minute, tzinfo=timezone.utc)


def stamp(published=t(18), captured=t(18, 5)):
    return SourceStamp("synthetic", "https://example.org/source",
                       published, captured, H)


def fixture():
    game = Game("NBA", "nba:synthetic", "team:home", "team:away", t(20))
    q1 = PropQuote("quote:one", game.event_id, "athlete:one", "team:home",
                   "points", "full_game", "over", "20.5", -110,
                   "synthetic-book", stamp())
    q2 = PropQuote("quote:two", game.event_id, "athlete:two", "team:away",
                   "assists", "full_game", "under", "7.5", 100,
                   "synthetic-book", stamp())
    q3 = PropQuote("quote:three", game.event_id, "athlete:three", "team:home",
                   "rebounds", "full_game", "over", "10.5", -120,
                   "synthetic-book", stamp())
    selected = tuple(FrozenPropSelection(
        "selection:" + suffix, q.quote_id, t(19), H)
        for suffix, q in zip(("one", "two", "three"), (q1, q2, q3))
    )
    obs1 = ObservedPlayerStat(
        game.event_id, q1.athlete_id, q1.team_id, q1.market,
        "full_game", "played", "22", True, stamp(t(22, 10), t(22, 15)))
    obs2 = ObservedPlayerStat(
        game.event_id, q2.athlete_id, q2.team_id, q2.market,
        "full_game", "played", "9", True, stamp(t(22, 10), t(22, 15)))
    final = EventFinalReceipt(
        game.event_id, game.home_team_id, game.away_team_id,
        t(22), stamp(t(22), t(22, 5)))
    return [game, selected, (q1, q2, q3), (obs1, obs2), final, t(23)]


def audit(case):
    return audit_frozen_prop_batch(*case)


class FrozenPropBatchTests(unittest.TestCase):
    def test_full_frozen_denominator_includes_missing_final(self):
        result = audit(fixture())
        self.assertTrue(result.structurally_valid, result.reasons)
        self.assertEqual(result.declared_frozen_denominator, 3)
        self.assertEqual(len(result.rows), 3)
        self.assertEqual((result.direction_matched, result.direction_missed,
                          result.pending, result.invalid), (1, 1, 1, 0))
        self.assertEqual(result.rows[2].status, "pending")
        self.assertIn("player_outcome_missing", result.rows[2].reasons)

    def test_original_order_preserved_no_winners_only_filter(self):
        case = fixture()
        self.assertEqual([r.selection_id for r in audit(case).rows],
                         [s.selection_id for s in case[1]])

    def test_flags_never_promote_research_to_scoring(self):
        result = audit(fixture())
        self.assertFalse(result.scoring_eligible)
        self.assertFalse(result.source_independently_verified)
        self.assertFalse(result.manifest_completeness_verified)
        self.assertFalse(result.official_book_settlement_verified)
        self.assertFalse(result.model_accuracy_established)
        self.assertTrue(all(not r.scoring_eligible for r in result.rows))

    def test_original_quote_line_and_side_retained(self):
        result = audit(fixture())
        self.assertEqual((result.rows[1].original_line, result.rows[1].original_side),
                         ("7.5", "under"))

    def test_no_selection_is_not_valid_denominator(self):
        case = fixture()
        case[1] = ()
        result = audit(case)
        self.assertFalse(result.structurally_valid)
        self.assertIn("frozen_selection_manifest_empty", result.reasons)

    def test_missing_original_quote_is_invalid_not_dropped(self):
        case = fixture()
        case[2] = case[2][:2]
        result = audit(case)
        self.assertEqual(result.declared_frozen_denominator, 3)
        self.assertEqual(result.invalid, 1)
        self.assertIn("original_quote_missing", result.rows[2].reasons)

    def test_ambiguous_duplicate_quote_ids_block_result(self):
        case = fixture()
        case[2] = case[2] + (replace(case[2][0], sportsbook="another"),)
        result = audit(case)
        self.assertEqual(result.invalid, 1)
        self.assertIn("ambiguous_original_quote_id", result.rows[0].reasons)

    def test_duplicate_frozen_selection_id_blocks_both_rows(self):
        case = fixture()
        case[1] = (case[1][0], replace(case[1][1],
                    selection_id=case[1][0].selection_id), case[1][2])
        result = audit(case)
        self.assertEqual(result.declared_frozen_denominator, 3)
        self.assertEqual(result.invalid, 2)
        self.assertIn("duplicate_frozen_selection_id", result.rows[0].reasons)
        self.assertIn("duplicate_frozen_selection_id", result.rows[1].reasons)

    def test_reused_quote_id_blocks_double_counting(self):
        case = fixture()
        case[1] = (case[1][0], replace(case[1][1],
                    quote_id=case[1][0].quote_id), case[1][2])
        result = audit(case)
        self.assertEqual(result.invalid, 2)
        self.assertIn("duplicate_selected_quote_id", result.rows[1].reasons)

    def test_selection_frozen_after_tip_is_invalid(self):
        case = fixture()
        case[1] = (replace(case[1][0], frozen_at=t(20, 1)),) + case[1][1:]
        self.assertIn("selection_frozen_at_or_after_tip",
                      audit(case).rows[0].reasons)

    def test_selection_frozen_at_tip_is_invalid(self):
        case = fixture()
        case[1] = (replace(case[1][0], frozen_at=t(20)),) + case[1][1:]
        self.assertIn("selection_frozen_at_or_after_tip",
                      audit(case).rows[0].reasons)

    def test_quote_captured_after_selection_freeze_is_invalid(self):
        case = fixture()
        case[2] = (replace(case[2][0],
                           source=stamp(t(19, 10), t(19, 15))),) + case[2][1:]
        self.assertIn("quote_captured_after_selection_freeze",
                      audit(case).rows[0].reasons)

    def test_quote_captured_after_tip_is_invalid(self):
        case = fixture()
        case[2] = (replace(case[2][0],
                           source=stamp(t(20, 1), t(20, 2))),) + case[2][1:]
        self.assertIn("quote_captured_at_or_after_tip",
                      audit(case).rows[0].reasons)

    def test_selection_frozen_after_review_cutoff_is_invalid(self):
        case = fixture()
        case[5] = t(18, 30)
        self.assertIn("selection_frozen_after_review_cutoff",
                      audit(case).rows[0].reasons)

    def test_review_at_tip_is_invalid(self):
        case = fixture()
        case[5] = t(20)
        result = audit(case)
        self.assertFalse(result.structurally_valid)
        self.assertEqual(result.invalid, 3)
        self.assertIn("batch_review_before_event_start", result.reasons)

    def test_quote_from_other_event_is_invalid(self):
        case = fixture()
        case[2] = (replace(case[2][0], event_id="nba:other"),) + case[2][1:]
        self.assertIn("original_quote_event_mismatch",
                      audit(case).rows[0].reasons)

    def test_quote_team_outside_event_is_invalid(self):
        case = fixture()
        case[2] = (replace(case[2][0], team_id="team:other"),) + case[2][1:]
        self.assertIn("original_quote_team_not_in_event",
                      audit(case).rows[0].reasons)

    def test_ambiguous_player_stat_corrections_fail_closed(self):
        case = fixture()
        case[3] = case[3] + (replace(case[3][0], actual_stat="19"),)
        result = audit(case)
        self.assertIn("ambiguous_stat_corrections_or_duplicate_observations",
                      result.rows[0].reasons)
        self.assertEqual(result.invalid, 1)
        self.assertEqual(result.direction_matched, 0)

    def test_identical_duplicate_stat_receipts_still_ambiguous(self):
        case = fixture()
        case[3] = case[3] + (case[3][0],)
        self.assertEqual(audit(case).rows[0].status, "invalid")

    def test_wrong_player_stat_never_used(self):
        case = fixture()
        case[3] = (replace(case[3][0], athlete_id="athlete:other"), case[3][1])
        result = audit(case)
        self.assertEqual(result.rows[0].status, "pending")
        self.assertEqual(result.unselected_observation_records, 1)

    def test_wrong_team_stat_never_used(self):
        case = fixture()
        case[3] = (replace(case[3][0], team_id="team:away"), case[3][1])
        self.assertEqual(audit(case).rows[0].status, "pending")

    def test_wrong_market_stat_never_used(self):
        case = fixture()
        case[3] = (replace(case[3][0], market="rebounds"), case[3][1])
        self.assertEqual(audit(case).rows[0].status, "pending")

    def test_orphan_observations_are_not_added_to_denominator(self):
        case = fixture()
        case[3] = case[3] + (replace(case[3][0], athlete_id="athlete:extra"),)
        result = audit(case)
        self.assertEqual(result.declared_frozen_denominator, 3)
        self.assertEqual(result.unselected_observation_records, 1)
        self.assertIn("unselected_observations_excluded_from_denominator",
                      result.reasons)

    def test_missing_final_receipt_blocks_mathematical_wins(self):
        case = fixture()
        case[4] = None
        result = audit(case)
        self.assertEqual(result.invalid, 2)
        self.assertEqual(result.pending, 1)
        self.assertIn("event_final_receipt_missing", result.rows[0].reasons)

    def test_false_final_stat_chronology_blocks_outcome(self):
        case = fixture()
        case[3] = (replace(case[3][0],
                    source=stamp(t(20, 5), t(20, 10))), case[3][1])
        result = audit(case)
        self.assertEqual(result.rows[0].status, "invalid")
        self.assertIn("player_stat_published_before_event_final",
                      result.rows[0].reasons)

    def test_retracted_or_corrected_stat_needs_versioned_selection(self):
        case = fixture()
        # Two candidate observations for the same original market:
        # neither may be chosen based on whether it wins the prop.
        case[3] = case[3] + (replace(case[3][0],
                    source=stamp(t(22, 20), t(22, 25)),
                    actual_stat="20"),)
        self.assertEqual(audit(case).rows[0].status, "invalid")

    def test_dnp_is_not_a_win_loss_or_void(self):
        case = fixture()
        q3 = case[2][2]
        dnp = ObservedPlayerStat(case[0].event_id, q3.athlete_id,
            q3.team_id, q3.market, "full_game", "dnp", None, True,
            stamp(t(22, 10), t(22, 15)))
        case[3] = case[3] + (dnp,)
        result = audit(case)
        self.assertEqual(result.dnp_needs_rules, 1)
        self.assertEqual(result.pending, 0)
        self.assertEqual(result.rows[2].status, "dnp_needs_rules")

    def test_push_is_separate_from_matched_direction(self):
        case = fixture()
        case[3] = (replace(case[3][0], actual_stat="20.5"), case[3][1])
        result = audit(case)
        self.assertEqual(result.pushes, 1)
        self.assertEqual(result.direction_matched, 0)

    def test_unknown_outcome_is_unresolved_not_miss(self):
        case = fixture()
        case[3] = (replace(case[3][0], participation="unknown",
                           actual_stat=None, source=None), case[3][1])
        result = audit(case)
        self.assertEqual(result.rows[0].status, "unresolved")
        self.assertEqual(result.direction_missed, 1)

    def test_unsupported_sport_market_fails_from_underlying_gate(self):
        case = fixture()
        case[2] = (replace(case[2][0], market="shots_on_goal"),) + case[2][1:]
        case[3] = (replace(case[3][0], market="shots_on_goal"),) + case[3][1:]
        result = audit(case)
        self.assertIn("market_period_mismatch", result.rows[0].reasons)

    def test_multi_book_quotes_keep_distinct_selection_denominators(self):
        case = fixture()
        q4 = replace(case[2][0], quote_id="quote:four",
                     sportsbook="another-book", line="21.5")
        case[2] = case[2] + (q4,)
        case[1] = case[1] + (
            FrozenPropSelection("selection:four", q4.quote_id, t(19), H),)
        result = audit(case)
        self.assertEqual(result.declared_frozen_denominator, 4)
        self.assertEqual(result.direction_matched, 2)
        self.assertEqual(result.rows[-1].original_line, "21.5")

    def test_nfl_player_prop_works_without_nba_scoring_assumption(self):
        case = fixture()
        gm = Game("NFL", "nfl:synthetic", "team:home", "team:away", t(20))
        q = replace(case[2][0], event_id=gm.event_id,
                    market="receiving_yards")
        obs = replace(case[3][0], event_id=gm.event_id,
                      market="receiving_yards")
        final = replace(case[4], event_id=gm.event_id)
        result = audit([gm, (case[1][0],), (q,), (obs,), final, t(23)])
        self.assertEqual(result.direction_matched, 1)
        self.assertFalse(result.scoring_eligible)

    def test_selection_id_and_hash_are_required(self):
        with self.assertRaises(ValueError):
            FrozenPropSelection("fake", "quote:one", t(19), H)
        with self.assertRaises(ValueError):
            FrozenPropSelection("selection:one", "quote:one", t(19), "bad")

    def test_freeze_must_be_timezone_aware(self):
        with self.assertRaises(ValueError):
            FrozenPropSelection("selection:one", "quote:one",
                                datetime(2026, 10, 25, 19), H)

    def test_frozen_manifest_rows_are_immutable(self):
        row = audit(fixture()).rows[0]
        with self.assertRaises(FrozenInstanceError):
            row.status = "selected_over_lost"

    def test_input_types_fail_closed(self):
        case = fixture()
        case[1] = [case[1][0]]
        with self.assertRaises(TypeError):
            audit(case)
        case = fixture()
        case[3] = [{"actual_stat": "22"}]
        with self.assertRaises(TypeError):
            audit(case)

    def test_repeated_runs_are_deterministic(self):
        case = fixture()
        self.assertEqual(audit(case), audit(case))


if __name__ == "__main__":
    unittest.main()
