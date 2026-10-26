"""Synthetic full-roster screening-manifest integrity tests; no real NBA data."""
from dataclasses import replace
import unittest

from research.props.nba_context_audit import audit_nba_prop_context
from research.props.nba_context_freeze_audit import audit_nba_frozen_bank
from research.props.nba_frozen_screen_manifest import (
    audit_nba_frozen_screen_manifest, nba_screen_manifest_sha256,
)
from research.props.prop_board import PropProjection, PropScreen, RosterAthlete
from research.tests.test_nba_context_audit import fixture, stamp, t


def make_receipt(case, day=25, hour=11):
    return stamp(day, hour, digest=nba_screen_manifest_sha256(
        case[0], case[1], case[2], case[3],
    ))


def audit(case, receipt=None):
    if receipt is None:
        receipt = make_receipt(case)
    return audit_nba_frozen_screen_manifest(
        case[0], case[1], case[2], case[3], case[4], receipt, case[9],
    )


class NBAFrozenScreenManifestTests(unittest.TestCase):
    def test_baseline_full_roster_screen_is_internally_consistent(self):
        result = audit(fixture())
        self.assertTrue(result.structurally_valid, result.reasons)
        self.assertTrue(result.full_declared_roster_screen)
        self.assertTrue(result.manifest_hash_matches_receipt)
        self.assertTrue(result.all_roster_sources_known_at_manifest)
        self.assertTrue(result.manifest_known_before_all_considered_inputs)
        self.assertEqual(result.expected_player_market_rows, 2)
        self.assertEqual(result.supplied_screen_rows, 2)
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(len(result.projection_rows), 1)
        self.assertFalse(result.external_archive_verified)
        self.assertFalse(result.independently_verified_roster_complete)
        self.assertFalse(result.production_scoring_authorized)
        self.assertFalse(result.play_authorized)

    def test_reproduces_parent_late_roster_evidence_gap(self):
        case = fixture()
        case[1] = (replace(case[1][0], source=stamp(25, 13)), case[1][1])
        # Both upstream audits can accept a roster snapshot published
        # *after* the projection's noon input cutoff but before 15:00 review.
        self.assertTrue(audit_nba_prop_context(*case, season="2026-27").
                        context_complete)
        self.assertTrue(audit_nba_frozen_bank(*case, season="2026-27").
                        context_complete)
        result = audit(case)
        self.assertFalse(result.structurally_valid)
        self.assertIn("roster_source_after_screen_manifest:athlete:one",
                      result.reasons)

    def test_late_bench_roster_not_silently_retroactive(self):
        case = fixture()
        case[1] = (case[1][0], replace(case[1][1], source=stamp(25, 13)))
        self.assertTrue(audit_nba_frozen_bank(*case, season="2026-27").
                        context_complete)
        result = audit(case)
        self.assertFalse(result.all_roster_sources_known_at_manifest)
        self.assertEqual(result.expected_player_market_rows, 2)
        self.assertEqual(len(result.rows), 2)
        self.assertIn("roster_source_after_screen_manifest:athlete:two",
                      result.reasons)

    def test_manifest_created_after_model_input_cutoff_fails(self):
        case = fixture()
        result = audit(case, make_receipt(case, hour=13))
        self.assertFalse(result.manifest_known_before_all_considered_inputs)
        self.assertIn("athlete:one:points:screen_manifest_not_frozen_before_projection_inputs",
                      result.reasons)

    def test_manifest_captured_at_exact_model_inputs_is_allowed(self):
        case = fixture()
        self.assertTrue(audit(case, make_receipt(case, hour=12)).
                        structurally_valid)

    def test_manifest_captured_after_board_cutoff_fails(self):
        case = fixture()
        result = audit(case, make_receipt(case, hour=16))
        self.assertIn("screen_manifest_receipt_not_known_pregame", result.reasons)

    def test_manifest_captured_after_tipoff_fails(self):
        case = fixture()
        result = audit(case, make_receipt(case, day=26, hour=9))
        self.assertIn("screen_manifest_receipt_not_known_pregame", result.reasons)

    def test_screen_decision_tamper_detected_against_original_receipt(self):
        case = fixture()
        original = make_receipt(case)
        case[3] = (replace(case[3][0], decision="exclude", reason="postgame edit"),
                   case[3][1])
        result = audit(case, original)
        self.assertFalse(result.manifest_hash_matches_receipt)
        self.assertIn("screen_manifest_content_hash_mismatch", result.reasons)

    def test_roster_identity_tamper_detected_against_original_receipt(self):
        case = fixture()
        original = make_receipt(case)
        case[1] = (replace(case[1][0], athlete_id="athlete:other"), case[1][1])
        self.assertFalse(audit(case, original).manifest_hash_matches_receipt)

    def test_bench_player_removed_from_original_manifest_detected(self):
        case = fixture()
        original = make_receipt(case)
        case[1] = (case[1][0],)
        case[3] = (case[3][0],)
        result = audit(case, original)
        self.assertTrue(result.full_declared_roster_screen is False)
        self.assertFalse(result.manifest_hash_matches_receipt)
        self.assertIn("both_event_teams_required", result.reasons)

    def test_extra_bench_player_missing_screen_is_not_full_roster(self):
        case = fixture()
        case[1] = case[1] + (
            RosterAthlete("athlete:bench", "team:home", "active", stamp(25, 9)),)
        result = audit(case)
        self.assertEqual(result.expected_player_market_rows, 3)
        self.assertEqual(result.supplied_screen_rows, 2)
        self.assertFalse(result.full_declared_roster_screen)
        self.assertIn("athlete:bench:points:missing_or_ambiguous_player_market_screen",
                      result.reasons)

    def test_duplicate_player_market_screen_is_ambiguous(self):
        case = fixture()
        case[3] = case[3] + (case[3][0],)
        result = audit(case)
        self.assertFalse(result.full_declared_roster_screen)
        self.assertIn("duplicate_player_market_screen:athlete:one:points",
                      result.reasons)

    def test_orphan_player_market_screen_fails(self):
        case = fixture()
        case[3] = case[3] + (
            PropScreen("athlete:orphan", "team:home", "points",
                       "exclude", "unknown"),)
        self.assertIn("orphan_player_market_screen:athlete:orphan:points",
                      audit(case).reasons)

    def test_wrong_team_screen_fails(self):
        case = fixture()
        case[3] = (replace(case[3][0], team_id="team:away"), case[3][1])
        self.assertIn("athlete:one:points:screen_team_mismatch",
                      audit(case).reasons)

    def test_unknown_player_considered_fails(self):
        case = fixture()
        case[3] = (case[3][0], replace(case[3][1], decision="consider",
                                       reason="narrative"))
        self.assertIn("athlete:two:points:ineligible_or_uncertain_player_considered",
                      audit(case).reasons)

    def test_questionable_player_excluded_instead_of_unresolved_fails(self):
        case = fixture()
        case[1] = (case[1][0], replace(case[1][1], availability="questionable"))
        case[3] = (case[3][0], replace(case[3][1], decision="exclude",
                                      reason="uncertain"))
        self.assertIn("athlete:two:points:uncertain_player_must_remain_unresolved",
                      audit(case).reasons)

    def test_duplicate_roster_identity_fails(self):
        case = fixture()
        case[1] = case[1] + (replace(case[1][0], team_id="team:away"),)
        self.assertIn("duplicate_roster_identity:athlete:one",
                      audit(case).reasons)

    def test_missing_considered_projection_fails(self):
        case = fixture()
        case[4] = ()
        self.assertIn("considered_player_projection_missing_or_ambiguous:athlete:one:points",
                      audit(case).reasons)

    def test_duplicate_considered_projection_fails(self):
        case = fixture()
        case[4] = case[4] + (replace(case[4][0], artifact_sha256="f" * 64),)
        self.assertIn("duplicate_player_market_projection:athlete:one:points",
                      audit(case).reasons)

    def test_projection_without_considered_screen_fails(self):
        case = fixture()
        case[4] = case[4] + (
            PropProjection("athlete:two", "team:away", "points", "17",
                           t(25, 12), t(25, 11), "f" * 64),)
        self.assertIn("projection_without_considered_screen:athlete:two:points",
                      audit(case).reasons)

    def test_projection_wrong_team_fails(self):
        case = fixture()
        case[4] = (replace(case[4][0], team_id="team:away"),)
        self.assertIn("athlete:one:points:projection_team_mismatch",
                      audit(case).reasons)

    def test_projection_frozen_after_board_review_fails(self):
        case = fixture()
        case[4] = (replace(case[4][0], frozen_at=t(25, 16)),)
        self.assertIn("athlete:one:points:screen_manifest_not_frozen_before_projection_inputs",
                      audit(case).reasons)

    def test_projection_frozen_after_tipoff_fails(self):
        case = fixture()
        case[4] = (replace(case[4][0], frozen_at=t(25, 21)),)
        self.assertFalse(audit(case).structurally_valid)

    def test_no_considered_players_is_valid_but_not_a_play(self):
        case = fixture()
        case[3] = (replace(case[3][0], decision="exclude", reason="no opportunity"),
                   case[3][1])
        case[4] = ()
        result = audit(case)
        self.assertTrue(result.structurally_valid, result.reasons)
        self.assertEqual(result.projection_rows, ())
        self.assertFalse(result.play_authorized)

    def test_hash_deterministic_under_roster_and_screen_order(self):
        case = fixture()
        digest = nba_screen_manifest_sha256(case[0], case[1], case[2], case[3])
        self.assertEqual(digest, nba_screen_manifest_sha256(
            case[0], tuple(reversed(case[1])), case[2],
            tuple(reversed(case[3])),
        ))

    def test_hash_binds_source_digest_and_capture(self):
        case = fixture()
        digest = nba_screen_manifest_sha256(case[0], case[1], case[2], case[3])
        case[1] = (replace(case[1][0], source=stamp(25, 9, digest="f" * 64)),
                   case[1][1])
        self.assertNotEqual(digest, nba_screen_manifest_sha256(
            case[0], case[1], case[2], case[3],
        ))

    def test_hash_binds_game_start_and_requested_markets(self):
        case = fixture()
        digest = nba_screen_manifest_sha256(case[0], case[1], case[2], case[3])
        self.assertNotEqual(digest, nba_screen_manifest_sha256(
            replace(case[0], scheduled_start=t(25, 21)),
            case[1], case[2], case[3],
        ))
        self.assertNotEqual(digest, nba_screen_manifest_sha256(
            case[0], case[1], ("points", "rebounds"), case[3],
        ))

    def test_hash_binds_reason_and_roster_availability(self):
        case = fixture()
        original = make_receipt(case)
        case[3] = (replace(case[3][0], reason="posthoc rationale"), case[3][1])
        self.assertFalse(audit(case, original).manifest_hash_matches_receipt)
        case = fixture()
        original = make_receipt(case)
        case[1] = (replace(case[1][0], availability="out"), case[1][1])
        self.assertFalse(audit(case, original).manifest_hash_matches_receipt)

    def test_malformed_inputs_fail_closed(self):
        case = fixture()
        with self.assertRaises(ValueError):
            audit_nba_frozen_screen_manifest(
                case[0], case[1], ("unknown_market",), case[3],
                case[4], make_receipt(case), case[9])
        with self.assertRaises(TypeError):
            audit_nba_frozen_screen_manifest(
                case[0], case[1], case[2], case[3],
                case[4], {"sha": "fake"}, case[9])

    def test_review_after_tipoff_rejected(self):
        case = fixture()
        case[9] = t(25, 20)
        with self.assertRaises(ValueError):
            audit(case)

    def test_declared_receipt_cannot_authenticate_itself(self):
        case = fixture()
        result = audit(case)
        self.assertTrue(result.manifest_hash_matches_receipt)
        self.assertFalse(result.external_archive_verified)
        self.assertFalse(result.independently_verified_roster_complete)
        self.assertFalse(result.production_scoring_authorized)

    def test_rewriting_manifest_and_hash_together_is_not_proof(self):
        case = fixture()
        case[3] = (replace(case[3][0], decision="exclude",
                           reason="posthoc downgrade"), case[3][1])
        case[4] = ()
        result = audit(case, make_receipt(case))
        self.assertTrue(result.structurally_valid, result.reasons)
        self.assertFalse(result.external_archive_verified)
        self.assertFalse(result.independently_verified_roster_complete)


if __name__ == "__main__":
    unittest.main()
