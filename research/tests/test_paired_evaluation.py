"""Synthetic unit tests for paired, frozen prospective research comparisons."""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from research.quality.paired_evaluation import evaluate_batch


H = "a" * 64


def batch(sport="NBA"):
    event = sport.lower() + ":event-01"
    second = sport.lower() + ":event-02"
    forecasts = [
        {"forecast_id": "forecasts:f1", "event_id": event,
         "athlete_id": "players:p1", "team_id": "teams:t1", "market": "points",
         "scheduled_start_utc": "2026-10-25T19:00:00Z",
         "frozen_at_utc": "2026-10-25T12:55:00Z",
         "training_data_as_of_utc": "2026-10-25T12:00:00Z",
         "baseline_data_as_of_utc": "2026-10-25T11:55:00Z",
         "baseline_frozen_at_utc": "2026-10-25T12:50:00Z",
         "predicted_value": 21, "baseline_value": 22},
        {"forecast_id": "forecasts:f2", "event_id": event,
         "athlete_id": "players:p2", "team_id": "teams:t2", "market": "points",
         "scheduled_start_utc": "2026-10-25T19:00:00Z",
         "frozen_at_utc": "2026-10-25T12:55:00Z",
         "training_data_as_of_utc": "2026-10-25T12:00:00Z",
         "baseline_data_as_of_utc": "2026-10-25T11:55:00Z",
         "baseline_frozen_at_utc": "2026-10-25T12:50:00Z",
         "predicted_value": 9, "baseline_value": 13},
        {"forecast_id": "forecasts:f3", "event_id": second,
         "athlete_id": "players:p3", "team_id": "teams:t3", "market": "points",
         "scheduled_start_utc": "2026-10-25T20:00:00Z",
         "frozen_at_utc": "2026-10-25T12:55:00Z",
         "training_data_as_of_utc": "2026-10-25T12:00:00Z",
         "baseline_data_as_of_utc": "2026-10-25T11:55:00Z",
         "baseline_frozen_at_utc": "2026-10-25T12:50:00Z",
         "predicted_value": 17, "baseline_value": 18},
    ]
    def settled(forecast, status, actual=None):
        return {"forecast_id": forecast["forecast_id"],
                "event_id": forecast["event_id"],
                "athlete_id": forecast["athlete_id"],
                "team_id": forecast["team_id"],
                "market": "points", "status": status,
                "actual_value": actual,
                "source_url": "https://stats.example.org/results",
                "published_at_utc": "2026-10-25T23:00:00Z",
                "captured_at_utc": "2026-10-25T23:01:00Z",
                "raw_sha256": H}
    return {
        "batch_id": "batch:20261025-01", "sport": sport,
        "market": "points", "model_version": "model:v1",
        "baseline_version": "baseline:naive-v1",
        "frozen_manifest_sha256": H,
        "baseline_artifact_sha256": H,
        "evaluation_protocol_sha256": H,
        "evaluation_protocol_frozen_at_utc": "2026-10-25T12:00:00Z",
        "frozen_manifest_at_utc": "2026-10-25T13:00:00Z",
        "evaluated_as_of_utc": "2026-10-26T02:00:00Z",
        "expected_forecast_ids": [f["forecast_id"] for f in forecasts],
        "forecasts": forecasts,
        "settlements": [settled(forecasts[0], "final", 24),
                        settled(forecasts[1], "final", 10),
                        settled(forecasts[2], "void")],
    }


class PairedEvaluationTests(unittest.TestCase):
    def test_verified_structure_never_promotes_to_scoring(self):
        report = evaluate_batch(batch())
        self.assertTrue(report.structurally_valid, report.reasons)
        self.assertTrue(report.evaluation_complete)
        self.assertFalse(report.production_eligible)
        self.assertFalse(report.scoring_eligible)
        self.assertIn("source_rights", report.independent_checks_required)

    def test_model_and_baseline_mae_use_identical_graded_cohort(self):
        report = evaluate_batch(batch())
        self.assertEqual(report.total_forecasts, 3)
        self.assertEqual((report.graded, report.voided, report.pending, report.no_decision),
                         (2, 1, 0, 0))
        self.assertEqual(report.model_mae, 2.0)
        self.assertEqual(report.baseline_mae, 2.5)
        self.assertEqual(report.paired_mae_improvement, 0.5)
        self.assertEqual((report.model_beats_baseline, report.baseline_beats_model,
                          report.tied), (1, 1, 0))
        self.assertEqual(report.unique_graded_events, 1)

    def test_applicable_to_multiple_sports(self):
        for sport in ("NBA", "NFL", "MLB", "NHL", "SOCCER"):
            with self.subTest(sport=sport):
                self.assertTrue(evaluate_batch(batch(sport)).structurally_valid)

    def test_not_a_document(self):
        self.assertIn("batch_not_object", evaluate_batch([]).reasons)

    def test_missing_prediction_array_fails(self):
        case = batch()
        case.pop("forecasts")
        self.assertIn("forecasts_missing", evaluate_batch(case).reasons)

    def test_missing_frozen_inventory_fails(self):
        case = batch()
        case.pop("expected_forecast_ids")
        self.assertIn("expected_id_inventory_invalid", evaluate_batch(case).reasons)

    def test_missing_winner_cannot_silently_drop_from_batch(self):
        case = batch()
        case["forecasts"].pop(1)
        self.assertIn("expected_id_inventory_mismatch", evaluate_batch(case).reasons)

    def test_missing_settlement_must_be_explicit_pending(self):
        case = batch()
        case["settlements"].pop()
        self.assertIn("settlement_inventory_mismatch", evaluate_batch(case).reasons)

    def test_unmatched_extra_settlement_fails(self):
        case = batch()
        case["settlements"][0]["forecast_id"] = "forecasts:unknown"
        report = evaluate_batch(case)
        self.assertIn("settlement_0_unmatched_forecast", report.reasons)

    def test_forecast_id_duplicate_fails(self):
        case = batch()
        case["forecasts"].append(copy.deepcopy(case["forecasts"][0]))
        self.assertIn("forecast_3_duplicate_id", evaluate_batch(case).reasons)

    def test_same_player_market_game_duplicate_fails(self):
        case = batch()
        case["forecasts"][1]["athlete_id"] = case["forecasts"][0]["athlete_id"]
        case["forecasts"][1]["team_id"] = case["forecasts"][0]["team_id"]
        self.assertIn("duplicate_player_event_market", evaluate_batch(case).reasons)

    def test_event_sport_namespace_required(self):
        case = batch()
        case["forecasts"][0]["event_id"] = "nfl:event-01"
        self.assertIn("forecast_0_event_id_invalid", evaluate_batch(case).reasons)

    def test_name_only_identity_rejected(self):
        case = batch()
        case["forecasts"][0]["athlete_id"] = "LeBron James"
        self.assertIn("forecast_0_athlete_or_team_id_invalid", evaluate_batch(case).reasons)

    def test_unqualified_id_rejected(self):
        case = batch()
        case["batch_id"] = "free text"
        self.assertIn("batch_id_invalid", evaluate_batch(case).reasons)

    def test_invalid_sport_and_market_fail(self):
        case = batch()
        case["sport"] = ["NBA"]
        case["market"] = {"points": True}
        report = evaluate_batch(case)
        self.assertIn("sport_invalid", report.reasons)
        self.assertIn("market_invalid", report.reasons)

    def test_cross_market_settlement_rejected(self):
        case = batch()
        case["settlements"][0]["market"] = "rebounds"
        self.assertIn("settlement_0_identity_mismatch", evaluate_batch(case).reasons)

    def test_cross_team_settlement_rejected(self):
        case = batch()
        case["settlements"][0]["team_id"] = "teams:other"
        self.assertIn("settlement_0_identity_mismatch", evaluate_batch(case).reasons)

    def test_prestart_training_cutoff_required(self):
        case = batch()
        case["forecasts"][0]["training_data_as_of_utc"] = "2026-10-25T18:00:00Z"
        self.assertIn("forecast_0_hindsight_or_poststart", evaluate_batch(case).reasons)

    def test_post_tip_frozen_prediction_rejected(self):
        case = batch()
        case["forecasts"][0]["frozen_at_utc"] = "2026-10-25T20:00:00Z"
        report = evaluate_batch(case)
        self.assertIn("forecast_0_hindsight_or_poststart", report.reasons)
        self.assertFalse(report.structurally_valid)

    def test_batch_manifest_must_freeze_before_earliest_tip(self):
        case = batch()
        case["frozen_manifest_at_utc"] = "2026-10-25T19:00:00Z"
        self.assertIn("forecast_0_manifest_late", evaluate_batch(case).reasons)

    def test_protocol_must_be_frozen_before_batch(self):
        case = batch()
        case["evaluation_protocol_frozen_at_utc"] = "2026-10-25T16:00:00Z"
        self.assertIn("protocol_or_evaluation_order_invalid", evaluate_batch(case).reasons)

    def test_invalid_hash_claims_rejected(self):
        case = batch()
        case["frozen_manifest_sha256"] = "foo"
        self.assertIn("frozen_manifest_digest_missing", evaluate_batch(case).reasons)

    def test_nan_and_infinite_predictions_rejected(self):
        for n in (float("nan"), float("inf"), float("-inf")):
            case = batch()
            case["forecasts"][0]["predicted_value"] = n
            with self.subTest(value=str(n)):
                report = evaluate_batch(case)
                self.assertIn("forecast_0_predicted_value_invalid", report.reasons)
                self.assertIsNone(report.model_mae)

    def test_nonfinite_actual_rejected(self):
        case = batch()
        case["settlements"][0]["actual_value"] = float("nan")
        self.assertIn("settlement_0_actual_invalid", evaluate_batch(case).reasons)

    def test_boolean_is_not_a_numeric_prediction(self):
        case = batch()
        case["forecasts"][0]["baseline_value"] = True
        self.assertIn("forecast_0_baseline_value_invalid", evaluate_batch(case).reasons)

    def test_pending_cannot_be_reported_as_complete(self):
        case = batch()
        case["settlements"][2] = {
            "forecast_id": case["forecasts"][2]["forecast_id"],
            "event_id": case["forecasts"][2]["event_id"],
            "athlete_id": case["forecasts"][2]["athlete_id"],
            "team_id": case["forecasts"][2]["team_id"],
            "market": "points", "status": "pending", "actual_value": None}
        report = evaluate_batch(case)
        self.assertTrue(report.structurally_valid, report.reasons)
        self.assertFalse(report.evaluation_complete)
        self.assertEqual(report.pending, 1)
        self.assertEqual(report.graded, 2)

    def test_pending_cannot_carry_final_result_or_source(self):
        case = batch()
        case["settlements"][0]["status"] = "pending"
        self.assertIn("settlement_0_nonfinal_has_actual", evaluate_batch(case).reasons)
        self.assertIn("settlement_0_pending_has_settlement_source",
                      evaluate_batch(case).reasons)

    def test_no_decision_preserved_in_denominator(self):
        case = batch()
        case["settlements"][2]["status"] = "no_decision"
        report = evaluate_batch(case)
        self.assertTrue(report.structurally_valid)
        self.assertEqual(report.no_decision, 1)
        self.assertEqual(report.total_forecasts, 3)

    def test_future_settlement_source_rejected(self):
        case = batch()
        case["settlements"][0]["captured_at_utc"] = "2026-10-27T00:00:00Z"
        self.assertIn("settlement_0_future_settlement", evaluate_batch(case).reasons)

    def test_final_cannot_be_captured_before_event_start(self):
        case = batch()
        case["settlements"][0]["published_at_utc"] = "2026-10-25T18:00:00Z"
        case["settlements"][0]["captured_at_utc"] = "2026-10-25T18:01:00Z"
        self.assertIn("settlement_0_final_before_start", evaluate_batch(case).reasons)

    def test_source_digest_and_https_required(self):
        case = batch()
        case["settlements"][0]["source_url"] = "http://untrusted.example"
        case["settlements"][0]["raw_sha256"] = "bad"
        self.assertIn("settlement_0_source_provenance_missing",
                      evaluate_batch(case).reasons)

    def test_duplicate_settlement_fails(self):
        case = batch()
        case["settlements"].append(copy.deepcopy(case["settlements"][0]))
        self.assertIn("settlement_3_duplicate_id", evaluate_batch(case).reasons)

    def test_malformed_records_cannot_crash(self):
        case = batch()
        case["forecasts"][0] = {"forecast_id": ["bad"]}
        case["settlements"][0] = ["bad"]
        report = evaluate_batch(case)
        self.assertFalse(report.structurally_valid)

    def test_missing_evaluations_cannot_manufacture_accuracy(self):
        case = batch()
        case["settlements"] = []
        report = evaluate_batch(case)
        self.assertFalse(report.structurally_valid)
        self.assertIsNone(report.model_mae)

    def test_baseline_must_freeze_before_prediction(self):
        case = batch()
        case["forecasts"][0]["baseline_frozen_at_utc"] = "2026-10-25T12:58:00Z"
        self.assertIn("forecast_0_baseline_not_prefrozen", evaluate_batch(case).reasons)

    def test_baseline_training_data_must_precede_its_freeze(self):
        case = batch()
        case["forecasts"][0]["baseline_data_as_of_utc"] = "2026-10-25T12:51:00Z"
        self.assertIn("forecast_0_baseline_not_prefrozen", evaluate_batch(case).reasons)

    def test_baseline_artifact_digest_required(self):
        case = batch()
        case.pop("baseline_artifact_sha256")
        self.assertIn("baseline_artifact_digest_missing", evaluate_batch(case).reasons)

    def test_same_athlete_on_opposing_teams_rejected(self):
        case = batch()
        case["forecasts"][1]["athlete_id"] = case["forecasts"][0]["athlete_id"]
        case["settlements"][1]["athlete_id"] = case["forecasts"][0]["athlete_id"]
        self.assertIn("athlete_assigned_multiple_teams_in_event",
                      evaluate_batch(case).reasons)

    def test_extreme_integer_cannot_crash_or_inflate_accuracy(self):
        case = batch()
        case["forecasts"][0]["predicted_value"] = 10 ** 2000
        report = evaluate_batch(case)
        self.assertIn("forecast_0_predicted_value_invalid", report.reasons)
        self.assertIsNone(report.model_mae)

    def test_cli_failure_on_invalid_inventory(self):
        case = batch()
        case["expected_forecast_ids"].pop()
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "batch.json"
            file.write_text(json.dumps(case), encoding="utf-8")
            cmd = [sys.executable, "-m", "research.quality.paired_evaluation", str(file)]
            run = subprocess.run(cmd, capture_output=True, text=True, check=False)
        self.assertEqual(run.returncode, 1)
        self.assertIn("expected_id_inventory_mismatch", run.stdout)

    def test_cli_success_does_not_authorize_scoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "batch.json"
            file.write_text(json.dumps(batch()), encoding="utf-8")
            run = subprocess.run(
                [sys.executable, "-m", "research.quality.paired_evaluation", str(file)],
                capture_output=True, text=True, check=False)
        self.assertEqual(run.returncode, 0)
        self.assertFalse(json.loads(run.stdout)["scoring_eligible"])


if __name__ == "__main__":
    unittest.main()
