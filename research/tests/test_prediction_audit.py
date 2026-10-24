"""Fixture-based regression checks for frozen prediction audit (offline)."""
import importlib.util
import os
import unittest

PATH = os.path.join(os.path.dirname(__file__), "..", "integrity", "prediction_audit.py")
SPEC = importlib.util.spec_from_file_location("prediction_audit", PATH)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def fixture():
    return {"frozen": True, "built_at_utc": "2026-10-24T12:00:00Z", "games": 1,
            "predictions": [{"player": "Example", "team": "AAA", "opponent": "BBB",
                             "event_id": "1", "tip_utc": "2026-10-24T22:00:00Z",
                             "logged_at_utc": "2026-10-24T11:59:00Z",
                             "mechanism": "FOUL_CAP", "direction": "DOWN",
                             "basis": "synthetic evidence", "grade": None}]}


class PredictionAuditTests(unittest.TestCase):
    def test_valid_log_is_not_betting_approved(self):
        result = AUDIT.audit(fixture())
        self.assertEqual(result["errors"], [])
        self.assertFalse(result["prop_ready"])

    def test_detects_opposite_direction_hypotheses(self):
        doc = fixture()
        doc["predictions"].append({**doc["predictions"][0], "mechanism": "CANNIBAL",
                                   "direction": "UP"})
        result = AUDIT.audit(doc)
        self.assertEqual(result["counts"]["opposite_direction_players"], 1)
        self.assertIn("opposite_direction_hypotheses_require_resolution", result["warnings"])

    def test_refuses_post_tip_log(self):
        doc = fixture()
        doc["predictions"][0]["logged_at_utc"] = "2026-10-24T23:00:00Z"
        self.assertTrue(any("not_logged_before_tip" in e for e in AUDIT.audit(doc)["errors"]))

    def test_refuses_post_tip_build(self):
        doc = fixture()
        doc["built_at_utc"] = "2026-10-24T23:00:00Z"
        self.assertTrue(any("build_not_before_tip" in e for e in AUDIT.audit(doc)["errors"]))

    def test_refuses_frozen_grade(self):
        doc = fixture()
        doc["predictions"][0]["grade"] = "HIT"
        self.assertTrue(any("frozen_log_contains_grade" in e for e in AUDIT.audit(doc)["errors"]))

    def test_refuses_duplicate_prediction(self):
        doc = fixture()
        doc["predictions"].append(dict(doc["predictions"][0]))
        self.assertTrue(any("duplicate_prediction" in e for e in AUDIT.audit(doc)["errors"]))

    def test_refuses_inconsistent_matchup(self):
        doc = fixture()
        doc["predictions"].append({**doc["predictions"][0], "team": "CCC", "opponent": "DDD"})
        self.assertTrue(any("inconsistent_matchup" in e for e in AUDIT.audit(doc)["errors"]))

    def test_flags_same_name_two_teams(self):
        doc = fixture()
        doc["predictions"].append({**doc["predictions"][0], "team": "BBB", "opponent": "AAA"})
        self.assertEqual(AUDIT.audit(doc)["counts"]["players_assigned_multiple_teams"], 1)

    def test_rejects_naive_timestamp(self):
        doc = fixture()
        doc["predictions"][0]["tip_utc"] = "2026-10-24T22:00:00"
        self.assertTrue(any("invalid_timestamp" in e for e in AUDIT.audit(doc)["errors"]))

    def test_missing_provenance_warning(self):
        self.assertTrue(any("missing_per_prediction_source_provenance" in w
                            for w in AUDIT.audit(fixture())["warnings"]))


if __name__ == "__main__":
    unittest.main()
