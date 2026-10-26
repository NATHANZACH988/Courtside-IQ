"""Synthetic regression tests for NBA watcher-to-grader source integrity."""
from copy import deepcopy
import unittest

from research.gameflow.prediction_log import grade_entry
from research.integrity.grade_source_audit import audit_pair, audit_batch


def prediction(mechanism="STEADY", **overrides):
    result = {"event_id": "401909853", "player": "Alex Smith",
              "team": "AAA", "opponent": "BBB", "mechanism": mechanism,
              "banked_pts_pg": 20, "banked_min_pg": 30}
    result.update(overrides)
    return result


def player(name="Alex Smith", team="AAA", **overrides):
    result = {"name": name, "team": team, "pos": "G", "starter": True,
              "min": "30", "pts": 20, "pf": 1, "fga": 10}
    result.update(overrides)
    return result


def watcher_final(**overrides):
    result = {"league": "nba", "event": "401909853", "status": "Final",
              "teams": {"AAA": 101, "BBB": 99},
              "segment_scores": {"AAA": [25, 25, 25, 26],
                                 "BBB": [25, 25, 25, 24]},
              "players": [player()], "notes": []}
    result.update(overrides)
    return result


class GradeSourceAuditTests(unittest.TestCase):
    def test_clean_identity_is_structural_only(self):
        result = audit_pair(prediction(), watcher_final())
        self.assertTrue(result.safe_for_legacy_grader)
        self.assertFalse(result.source_independently_verified)
        self.assertFalse(result.production_scoring_authorized)
        self.assertIn("stable_athlete_id_unavailable", result.warnings)
        self.assertIn("final_source_receipt_not_complete", result.warnings)

    def test_wrong_team_name_join_would_change_grade(self):
        # Existing legacy grader uses next(name match), regardless of team.
        fin = watcher_final(players=[
            player(team="BBB", pts=30), player(team="AAA", pts=4)])
        observed, _ = grade_entry(prediction(), fin)
        self.assertEqual(observed, "HIT")  # first wrong-team row, not actual AAA
        audit = audit_pair(prediction(), fin)
        self.assertFalse(audit.safe_for_legacy_grader)
        self.assertIn("ambiguous_name_only_player_join", audit.errors)

    def test_single_wrong_team_player_rejected(self):
        result = audit_pair(prediction(), watcher_final(players=[player(team="BBB")]))
        self.assertIn("player_team_mismatch_in_final", result.errors)

    def test_duplicate_same_team_player_rejected(self):
        result = audit_pair(prediction(), watcher_final(players=[player(), player()]))
        self.assertIn("ambiguous_name_only_player_join", result.errors)

    def test_cannibal_watcher_margin_mismatch_is_reproduced(self):
        fin = watcher_final(
            teams={"AAA": 125, "BBB": 95},
            players=[player(name="Starter Guard", pts=10, fga=4),
                     player(name="Alex Smith", starter=False, min="20", pts=15, fga=12)])
        observed, _ = grade_entry(prediction("CANNIBAL"), fin)
        self.assertEqual(observed, "HIT")  # skips margin: 'segments' absent
        audit = audit_pair(prediction("CANNIBAL"), fin)
        self.assertFalse(audit.safe_for_legacy_grader)
        self.assertEqual(audit.final_margin, 30)
        self.assertIn("legacy_cannibal_blownout_gate_skipped", audit.errors)
        self.assertIn("cannibal_final_margin_at_least_20", audit.errors)

    def test_cannibal_gate_skipped_even_when_game_is_close(self):
        audit = audit_pair(prediction("CANNIBAL"), watcher_final())
        self.assertIn("legacy_cannibal_blownout_gate_skipped", audit.errors)

    def test_cannibal_custom_segments_still_not_proven(self):
        fin = watcher_final(segments=[{"home": 2, "away": 1}])
        audit = audit_pair(prediction("CANNIBAL"), fin)
        self.assertTrue(audit.safe_for_legacy_grader)
        self.assertIn("legacy_segment_margin_semantics_unverified", audit.warnings)

    def test_retracted_foul_note_would_count_as_hit(self):
        fin = watcher_final(
            players=[player(pf=1, pts=22)],
            notes=[{"type": "foul_trouble_cap", "team": "AAA",
                    "player": "Alex Smith", "retracted": True}])
        observed, _ = grade_entry(prediction("FOUL_CAP"), fin)
        self.assertEqual(observed, "HIT")  # despite only one PF and retraction
        audit = audit_pair(prediction("FOUL_CAP"), fin)
        self.assertIn("foul_note_retracted_but_legacy_grader_counts_it", audit.errors)

    def test_wrong_team_foul_note_would_count_as_hit(self):
        fin = watcher_final(
            players=[player(pf=1, pts=22)],
            notes=[{"type": "foul_trouble_cap", "team": "BBB",
                    "player": "Alex Smith"}])
        observed, _ = grade_entry(prediction("FOUL_CAP"), fin)
        self.assertEqual(observed, "HIT")
        self.assertIn("foul_note_wrong_or_missing_team",
                      audit_pair(prediction("FOUL_CAP"), fin).errors)

    def test_retracted_status_string_caught(self):
        for status in ("retracted", "withdrawn", "superseded"):
            with self.subTest(status=status):
                fin = watcher_final(notes=[{"type": "foul_trouble_cap",
                                            "team": "AAA", "player": "Alex Smith",
                                            "status": status}])
                self.assertIn("foul_note_retracted_but_legacy_grader_counts_it",
                              audit_pair(prediction("FOUL_CAP"), fin).errors)

    def test_unrelated_note_does_not_block(self):
        fin = watcher_final(notes=[{"type": "bench_usage_surge",
                                    "team": "AAA", "bench_player": "Alex Smith"}])
        self.assertTrue(audit_pair(prediction("FOUL_CAP"), fin).
                        safe_for_legacy_grader)

    def test_valid_foul_note_provenance_is_only_a_warning(self):
        fin = watcher_final(notes=[{"type": "foul_trouble_cap",
                                    "team": "AAA", "player": "Alex Smith"}])
        result = audit_pair(prediction("FOUL_CAP"), fin)
        self.assertTrue(result.safe_for_legacy_grader)
        self.assertIn("foul_note_provenance_not_attached", result.warnings)

    def test_event_id_mismatch_rejected(self):
        self.assertIn("final_event_mismatch",
                      audit_pair(prediction(), watcher_final(event="401909999")).errors)

    def test_final_missing_event_rejected(self):
        fin = watcher_final()
        del fin["event"]
        self.assertIn("final_event_mismatch", audit_pair(prediction(), fin).errors)

    def test_nfl_final_cannot_grade_nba(self):
        self.assertIn("final_league_not_nba",
                      audit_pair(prediction(), watcher_final(league="nfl")).errors)

    def test_in_progress_final_rejected(self):
        self.assertIn("final_not_final",
                      audit_pair(prediction(), watcher_final(status="In Progress")).errors)

    def test_matchup_mismatch_rejected(self):
        self.assertIn("prediction_matchup_not_in_final",
                      audit_pair(prediction(), watcher_final(
                          teams={"AAA": 100, "CCC": 90})).errors)

    def test_player_team_outside_matchup_rejected(self):
        self.assertIn("final_player_team_not_in_matchup",
                      audit_pair(prediction(), watcher_final(
                          players=[player(team="CCC")])).errors)

    def test_invalid_team_score_types_rejected(self):
        for scores in ({"AAA": True, "BBB": 100}, {"AAA": -1, "BBB": 100},
                       {"AAA": 90}, {"AAA": 99, "BBB": 100.5}):
            with self.subTest(scores=scores):
                self.assertIn("final_team_scores_invalid",
                              audit_pair(prediction(), watcher_final(teams=scores)).errors)

    def test_missing_player_can_only_be_no_decision(self):
        result = audit_pair(prediction(), watcher_final(
            players=[player(name="Another Player")]))
        self.assertTrue(result.safe_for_legacy_grader)
        self.assertIn("player_absent_from_final_box_no_decision_expected",
                      result.warnings)

    def test_invalid_player_and_note_lists_rejected(self):
        self.assertIn("final_players_not_list",
                      audit_pair(prediction(), watcher_final(players=None)).errors)
        self.assertIn("final_notes_not_list",
                      audit_pair(prediction(), watcher_final(notes=None)).errors)
        self.assertIn("final_player_not_object",
                      audit_pair(prediction(), watcher_final(players=[None])).errors)
        self.assertIn("note_0_not_object",
                      audit_pair(prediction(), watcher_final(notes=[None])).errors)

    def test_bad_prediction_rejected(self):
        self.assertIn("prediction_not_object", audit_pair(None, watcher_final()).errors)
        self.assertIn("unknown_mechanism",
                      audit_pair(prediction("MYSTERY"), watcher_final()).errors)
        self.assertIn("event_id_not_valid_espn_nba_id",
                      audit_pair(prediction(event_id="../../etc"), watcher_final()).errors)
        self.assertIn("prediction_opponent_invalid",
                      audit_pair(prediction(opponent="AAA"), watcher_final()).errors)

    def test_non_dict_final_rejected(self):
        result = audit_pair(prediction(), None)
        self.assertFalse(result.safe_for_legacy_grader)
        self.assertIn("final_not_object", result.errors)

    def test_synthetic_receipt_still_not_independent_verification(self):
        fin = watcher_final(source_url="https://example.org/receipt",
                            captured_at_utc="2026-10-25T22:00:00Z",
                            raw_sha256="a" * 64)
        result = audit_pair(prediction(), fin)
        self.assertTrue(result.safe_for_legacy_grader)
        self.assertIn("source_receipt_claim_not_independently_verified", result.warnings)
        self.assertFalse(result.source_independently_verified)

    def test_bad_timestamp_receipt_is_incomplete(self):
        fin = watcher_final(source_url="https://example.org/receipt",
                            captured_at_utc="2026-10-25T22:00:00",
                            raw_sha256="a" * 64)
        self.assertIn("final_source_receipt_not_complete",
                      audit_pair(prediction(), fin).warnings)

    def test_batch_preserves_pending_and_unsafe_denominator(self):
        frozen = {"frozen": True, "predictions": [
            prediction(), prediction(event_id="401909854", player="Other"),
            prediction(event_id="401909855", player="Other"),
        ]}
        finals = {"401909853": watcher_final(),
                  "401909855": watcher_final(event="401909855", league="nfl")}
        result = audit_batch(frozen, finals)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["pending"], 1)
        self.assertEqual(result["unsafe"], 1)
        self.assertFalse(result["valid"])
        self.assertFalse(result["production_scoring_authorized"])

    def test_batch_with_only_valid_final_is_structurally_valid(self):
        frozen = {"frozen": True, "predictions": [prediction()]}
        result = audit_batch(frozen, {"401909853": watcher_final()})
        self.assertTrue(result["valid"])
        self.assertFalse(result["source_independently_verified"])
        self.assertFalse(result["production_scoring_authorized"])

    def test_batch_missing_final_remains_pending(self):
        frozen = {"frozen": True, "predictions": [prediction()]}
        result = audit_batch(frozen, {})
        self.assertTrue(result["valid"])
        self.assertEqual(result["pending"], 1)
        self.assertEqual(result["total"], 1)

    def test_batch_rejects_nonfrozen_input(self):
        self.assertFalse(audit_batch({"frozen": False, "predictions": [prediction()]},
                                     {"401909853": watcher_final()})["valid"])

    def test_batch_rejects_bad_inventory(self):
        self.assertFalse(audit_batch({"frozen": True, "predictions": []}, {})["valid"])
        self.assertFalse(audit_batch({"frozen": True, "predictions": [prediction()]},
                                     [])["valid"])

    def test_batch_rejects_unsafe_event_id_without_looking_up_file(self):
        frozen = {"frozen": True, "predictions": [prediction(event_id="../../etc")]}
        result = audit_batch(frozen, {})
        self.assertEqual(result["unsafe"], 1)
        self.assertEqual(result["pending"], 0)
        self.assertEqual(result["total"], 1)


if __name__ == "__main__":
    unittest.main()
