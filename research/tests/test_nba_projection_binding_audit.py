"""Synthetic-only tests for frozen NBA prop value/receipt binding."""
from dataclasses import replace
import unittest

from research.props.nba_frozen_screen_manifest import (
    audit_nba_frozen_screen_manifest, nba_screen_manifest_sha256,
)
from research.props.nba_projection_binding_audit import (
    FrozenNBAProjectionReceipt, audit_nba_projection_bindings,
    nba_projection_binding_record_sha256, nba_projection_content_sha256,
)
from research.props.prop_board import PropProjection, PropScreen, RosterAthlete
from research.tests.test_nba_context_audit import fixture, stamp, t


def screen_receipt(case):
    return stamp(25, 11, digest=nba_screen_manifest_sha256(
        case[0], case[1], case[2], case[3],
    ))


def projection_receipt(case, *, hour=13, minute=15):
    game, projection = case[0], case[4][0]
    screen_hash = nba_screen_manifest_sha256(
        case[0], case[1], case[2], case[3],
    )
    projection_hash = nba_projection_content_sha256(game, projection)
    archive_digest = nba_projection_binding_record_sha256(
        game, projection, screen_hash, projection_hash,
    )
    return FrozenNBAProjectionReceipt(
        projection.athlete_id, projection.team_id, projection.market,
        screen_hash, projection_hash,
        stamp(25, hour, minute, digest=archive_digest),
    )


def audit(case, receipt=None, bindings=None):
    if receipt is None:
        receipt = screen_receipt(case)
    if bindings is None:
        bindings = (projection_receipt(case),)
    return audit_nba_projection_bindings(
        case[0], case[1], case[2], case[3], case[4],
        receipt, bindings, case[5], case[9],
    )


class NBAProjectionBindingTests(unittest.TestCase):
    def test_baseline_full_roster_and_projection_bound(self):
        result = audit(fixture())
        self.assertTrue(result.structurally_valid, result.reasons)
        self.assertTrue(result.full_roster_screen_valid)
        self.assertEqual((result.considered_player_market_count,
                          result.bound, result.invalid, result.missing_receipts),
                         (1, 1, 0, 0))
        self.assertEqual(result.rows[0].quote_count, 1)
        self.assertFalse(result.play_authorized)
        self.assertFalse(result.scoring_authorized)
        self.assertFalse(result.external_archive_verified)
        self.assertFalse(result.independently_verified_original_predictions)
        self.assertFalse(result.prediction_accuracy_established)

    def test_reproduces_upstream_projection_value_gap(self):
        case = fixture()
        original_screen = screen_receipt(case)
        original_projection = projection_receipt(case)
        case[4] = (replace(case[4][0], predicted_stat="30.0"),)
        # PR #25 binds screens, not the numeric value of the projection.
        parent = audit_nba_frozen_screen_manifest(
            case[0], case[1], case[2], case[3], case[4],
            original_screen, case[9],
        )
        self.assertTrue(parent.structurally_valid, parent.reasons)
        result = audit(case, original_screen, (original_projection,))
        self.assertFalse(result.structurally_valid)
        self.assertIn("frozen_projection_content_changed", result.rows[0].reasons)

    def test_prediction_value_changed_to_favorable_outcome_fails(self):
        case = fixture()
        binding = projection_receipt(case)
        case[4] = (replace(case[4][0], predicted_stat="25.5"),)
        self.assertIn("frozen_projection_content_changed",
                      audit(case, bindings=(binding,)).rows[0].reasons)

    def test_prediction_value_changed_to_unfavorable_outcome_fails(self):
        case = fixture()
        binding = projection_receipt(case)
        case[4] = (replace(case[4][0], predicted_stat="19.5"),)
        self.assertFalse(audit(case, bindings=(binding,)).structurally_valid)

    def test_projection_inputs_timestamp_change_fails(self):
        case = fixture()
        binding = projection_receipt(case)
        case[4] = (replace(case[4][0], inputs_as_of=t(25, 11)),)
        self.assertIn("frozen_projection_content_changed",
                      audit(case, bindings=(binding,)).rows[0].reasons)

    def test_projection_freeze_timestamp_change_fails(self):
        case = fixture()
        binding = projection_receipt(case)
        case[4] = (replace(case[4][0], frozen_at=t(25, 13, 30)),)
        self.assertIn("frozen_projection_content_changed",
                      audit(case, bindings=(binding,)).rows[0].reasons)

    def test_projection_artifact_digest_change_fails(self):
        case = fixture()
        binding = projection_receipt(case)
        case[4] = (replace(case[4][0], artifact_sha256="c" * 64),)
        self.assertIn("frozen_projection_content_changed",
                      audit(case, bindings=(binding,)).rows[0].reasons)

    def test_archive_digest_tampering_fails(self):
        case = fixture()
        binding = projection_receipt(case)
        binding = replace(binding, archive_source=stamp(25, 13, 15, digest="d" * 64))
        self.assertIn("projection_archive_payload_digest_mismatch",
                      audit(case, bindings=(binding,)).rows[0].reasons)

    def test_binding_to_different_projection_hash_fails(self):
        case = fixture()
        binding = replace(projection_receipt(case), projection_sha256="d" * 64)
        self.assertIn("frozen_projection_content_changed",
                      audit(case, bindings=(binding,)).rows[0].reasons)

    def test_binding_to_different_screen_hash_fails(self):
        case = fixture()
        binding = replace(projection_receipt(case), screen_manifest_sha256="d" * 64)
        self.assertIn("projection_not_bound_to_original_screen_manifest",
                      audit(case, bindings=(binding,)).rows[0].reasons)

    def test_changed_screen_reasons_fail_original_receipt(self):
        case = fixture()
        original_screen = screen_receipt(case)
        original_projection = projection_receipt(case)
        case[3] = (replace(case[3][0], reason="revised after game"), case[3][1])
        result = audit(case, original_screen, (original_projection,))
        self.assertFalse(result.full_roster_screen_valid)
        self.assertFalse(result.structurally_valid)

    def test_archive_published_before_projection_freeze_fails(self):
        case = fixture()
        binding = projection_receipt(case)
        binding = replace(binding, archive_source=stamp(
            25, 12, digest=binding.archive_source.raw_sha256))
        self.assertIn("projection_archive_published_before_freeze",
                      audit(case, bindings=(binding,)).rows[0].reasons)

    def test_archive_captured_before_projection_freeze_fails(self):
        case = fixture()
        binding = projection_receipt(case)
        binding = replace(binding, archive_source=stamp(
            25, 12, 30, digest=binding.archive_source.raw_sha256))
        self.assertIn("projection_archive_captured_before_freeze",
                      audit(case, bindings=(binding,)).rows[0].reasons)

    def test_archive_after_quote_capture_fails(self):
        case = fixture()
        binding = projection_receipt(case, hour=14, minute=30)
        self.assertIn("quote_before_projection_archive:quote:one",
                      audit(case, bindings=(binding,)).rows[0].reasons)

    def test_archive_after_pretip_review_fails(self):
        case = fixture()
        binding = projection_receipt(case, hour=16)
        self.assertIn("projection_archive_not_known_pregame",
                      audit(case, bindings=(binding,)).rows[0].reasons)

    def test_archive_after_tipoff_fails(self):
        case = fixture()
        binding = projection_receipt(case, hour=21)
        self.assertIn("projection_archive_not_known_pregame",
                      audit(case, bindings=(binding,)).rows[0].reasons)

    def test_quote_capture_before_projection_freeze_fails(self):
        case = fixture()
        case[5] = (replace(case[5][0], source=stamp(25, 12, 45)),)
        self.assertIn("quote_before_projection_freeze:quote:one",
                      audit(case).rows[0].reasons)

    def test_quote_capture_before_archive_fails(self):
        case = fixture()
        case[5] = (replace(case[5][0], source=stamp(25, 13, 5)),)
        self.assertIn("quote_before_projection_archive:quote:one",
                      audit(case).rows[0].reasons)

    def test_late_quote_after_board_cutoff_fails(self):
        case = fixture()
        case[5] = (replace(case[5][0], source=stamp(25, 16)),)
        self.assertIn("quote_not_known_pregame:quote:one", audit(case).reasons)

    def test_wrong_event_quote_fails(self):
        case = fixture()
        case[5] = (replace(case[5][0], event_id="nba:wrong"),)
        self.assertIn("quote_wrong_event_or_team:quote:one", audit(case).reasons)

    def test_wrong_team_quote_fails(self):
        case = fixture()
        case[5] = (replace(case[5][0], team_id="team:away"),)
        self.assertIn("quote_player_team_mismatch:quote:one",
                      audit(case).rows[0].reasons)

    def test_missing_original_quote_fails(self):
        case = fixture()
        case[5] = ()
        result = audit(case)
        self.assertIn("original_posted_market_quote_missing", result.rows[0].reasons)

    def test_multiple_quotes_can_be_bound_if_both_after_archive(self):
        case = fixture()
        case[5] = case[5] + (replace(case[5][0], quote_id="quote:two",
                                    sportsbook="other-book", source=stamp(25, 14, 30)),)
        result = audit(case)
        self.assertTrue(result.structurally_valid, result.reasons)
        self.assertEqual(result.rows[0].quote_count, 2)

    def test_duplicate_original_quote_id_fails(self):
        case = fixture()
        case[5] = case[5] + (replace(case[5][0], sportsbook="other-book"),)
        result = audit(case)
        self.assertIn("duplicate_original_quote_id:quote:one", result.reasons)
        self.assertFalse(result.structurally_valid)

    def test_conflicting_same_book_side_quote_fails(self):
        case = fixture()
        case[5] = case[5] + (replace(case[5][0], quote_id="quote:second",
                                    line="25.5"),)
        result = audit(case)
        self.assertIn("ambiguous_original_book_side_quote:quote:one",
                      result.reasons)
        self.assertFalse(result.structurally_valid)

    def test_orphan_original_quote_not_in_roster_fails(self):
        case = fixture()
        case[5] = case[5] + (replace(case[5][0], quote_id="quote:other",
                                    athlete_id="athlete:other",
                                    sportsbook="other-book"),)
        self.assertIn("quote_not_in_frozen_player_roster:quote:other",
                      audit(case).reasons)

    def test_upstream_screen_invalid_does_not_count_projection_bound(self):
        case = fixture()
        original_receipt = screen_receipt(case)
        original_binding = projection_receipt(case)
        case[3] = (replace(case[3][0], reason="late revision"), case[3][1])
        result = audit(case, original_receipt, (original_binding,))
        self.assertEqual(result.bound, 0)
        self.assertIn("upstream_full_roster_screen_invalid",
                      result.rows[0].reasons)

    def test_duplicate_projection_fails(self):
        case = fixture()
        case[4] = case[4] + (case[4][0],)
        self.assertIn("ambiguous_projection_values:athlete:one:points",
                      audit(case).reasons)

    def test_missing_projection_fails(self):
        case = fixture()
        binding = projection_receipt(case)
        case[4] = ()
        self.assertIn("missing_or_ambiguous_projection",
                      audit(case, bindings=(binding,)).rows[0].reasons)

    def test_duplicate_binding_fails(self):
        case = fixture()
        binding = projection_receipt(case)
        result = audit(case, bindings=(binding, binding))
        self.assertIn("ambiguous_projection_receipts:athlete:one:points",
                      result.reasons)
        self.assertFalse(result.structurally_valid)

    def test_missing_binding_fails(self):
        result = audit(fixture(), bindings=())
        self.assertEqual(result.missing_receipts, 1)
        self.assertIn("missing_or_ambiguous_projection_receipt", result.rows[0].reasons)

    def test_orphan_binding_fails(self):
        case = fixture()
        original = projection_receipt(case)
        orphan = replace(original, athlete_id="athlete:other")
        self.assertIn("orphan_projection_receipt:athlete:other:points",
                      audit(case, bindings=(original, orphan)).reasons)

    def test_wrong_team_binding_fails(self):
        case = fixture()
        binding = replace(projection_receipt(case), team_id="team:away")
        self.assertIn("binding_team_mismatch", audit(case, bindings=(binding,)).rows[0].reasons)

    def test_frozen_screen_manifest_late_blocks_binding(self):
        case = fixture()
        receipt = stamp(25, 13, digest=nba_screen_manifest_sha256(
            case[0], case[1], case[2], case[3]))
        self.assertFalse(audit(case, receipt=receipt).structurally_valid)

    def test_zero_considered_players_valid_no_play(self):
        case = fixture()
        case[3] = (replace(case[3][0], decision="exclude", reason="no opportunity"),
                   case[3][1])
        case[4], case[5] = (), ()
        result = audit(case, bindings=())
        self.assertTrue(result.structurally_valid, result.reasons)
        self.assertEqual(result.considered_player_market_count, 0)
        self.assertEqual(result.rows, ())
        self.assertFalse(result.play_authorized)

    def test_late_added_bench_player_still_requires_screen(self):
        case = fixture()
        case[1] = case[1] + (
            RosterAthlete("athlete:bench", "team:home", "active", stamp(25, 9)),)
        self.assertFalse(audit(case).structurally_valid)

    def test_multiple_considered_markets_need_separate_receipts(self):
        case = fixture()
        case[2] = ("points", "rebounds")
        case[3] = case[3] + (
            PropScreen("athlete:one", "team:home", "rebounds", "consider", "active"),
            PropScreen("athlete:two", "team:away", "rebounds", "unresolved", "unknown"),
        )
        case[4] = case[4] + (
            replace(case[4][0], market="rebounds", artifact_sha256="d" * 64),)
        case[5] = case[5] + (
            replace(case[5][0], quote_id="quote:rebounds", market="rebounds"),)
        binding = projection_receipt(case)
        result = audit(case, bindings=(binding,))
        self.assertIn("missing_or_ambiguous_projection_receipt",
                      next(row for row in result.rows if row.market == "rebounds").reasons)

    def test_exact_projection_content_hash_deterministic(self):
        case = fixture()
        self.assertEqual(
            nba_projection_content_sha256(case[0], case[4][0]),
            nba_projection_content_sha256(case[0], case[4][0]),
        )
        self.assertNotEqual(
            nba_projection_content_sha256(case[0], case[4][0]),
            nba_projection_content_sha256(
                case[0], replace(case[4][0], predicted_stat="22.00")),
        )

    def test_changing_game_start_changes_projection_digest(self):
        case = fixture()
        projection = case[4][0]
        self.assertNotEqual(
            nba_projection_content_sha256(case[0], projection),
            nba_projection_content_sha256(
                replace(case[0], scheduled_start=t(25, 21)), projection),
        )

    def test_malformed_archive_receipt_rejected(self):
        case = fixture()
        binding = projection_receipt(case)
        with self.assertRaises(TypeError):
            replace(binding, archive_source={"hash": "unverified"})
        with self.assertRaises(TypeError):
            audit_nba_projection_bindings(
                case[0], case[1], case[2], case[3], case[4],
                screen_receipt(case), ({"fake": "binding"},), case[5], case[9])

    def test_recreating_projection_and_receipt_is_not_independent_proof(self):
        case = fixture()
        case[4] = (replace(case[4][0], predicted_stat="27.5"),)
        # Caller can rewrite BOTH alleged pregame records. Internal
        # consistency alone cannot certify original historical content.
        result = audit(case)
        self.assertTrue(result.structurally_valid, result.reasons)
        self.assertFalse(result.external_archive_verified)
        self.assertFalse(result.independently_verified_original_predictions)

    def test_projection_receipt_does_not_authorize_scoring(self):
        result = audit(fixture())
        self.assertTrue(result.structurally_valid)
        self.assertFalse(result.scoring_authorized)
        self.assertFalse(result.prediction_accuracy_established)


if __name__ == "__main__":
    unittest.main()
