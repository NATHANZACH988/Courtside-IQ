"""Synthetic integrity checks; these are not historical backtests."""
import copy
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "provenance" / "pregame_prediction_audit.py"
SPEC = importlib.util.spec_from_file_location("pregame_prediction_audit", PATH)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def fixture():
    return {"frozen": True, "date": "2026-10-28", "games": 1,
            "built_at_utc": "2026-10-28T12:00:00Z",
            "finals_banked_at_build": 28,
            "predictions": [{"event_id": "game1", "player": "Example Player",
                             "team": "SAS", "opponent": "UTA", "tip_utc": "2026-10-28T23:00:00Z",
                             "mechanism": "FOUL_CAP", "direction": "DOWN",
                             "banked_pts_pg": 20.0, "banked_min_pg": 30.0,
                             "thin_sample": False, "grade": None,
                             "logged_at_utc": "2026-10-28T12:00:00Z"}]}


class AuditTests(unittest.TestCase):
    def test_valid_claims_are_not_external_proof(self):
        result = MOD.audit(fixture())
        self.assertEqual(result["entries"], 1)
        self.assertFalse(result["independent_timestamp_verified"])
        self.assertFalse(result["pregame_bank_cutoff_verified"])

    def test_empty_prediction_cohort_rejected(self):
        d = fixture()
        d["predictions"] = []
        with self.assertRaisesRegex(ValueError, "nonempty list"):
            MOD.audit(d)

    def test_missing_or_invalid_cohort_date_rejected(self):
        for value in (None, "2026-02-30", "20261028", "2026-10-28junk"):
            with self.subTest(value=value):
                d = fixture()
                d["date"] = value
                with self.assertRaisesRegex(ValueError, "date:"):
                    MOD.audit(d)

    def test_invalid_declared_game_count_rejected(self):
        for value in (None, 0, -1, True, 1.0):
            with self.subTest(value=value):
                d = fixture()
                d["games"] = value
                with self.assertRaisesRegex(ValueError, "games:"):
                    MOD.audit(d)

    def test_more_events_than_declared_games_rejected(self):
        d = fixture()
        second = copy.deepcopy(d["predictions"][0])
        second["event_id"] = "game2"
        second["team"] = "NYK"
        second["opponent"] = "BOS"
        d["predictions"].append(second)
        with self.assertRaisesRegex(ValueError, "fewer scheduled games"):
            MOD.audit(d)

    def test_declared_cohort_not_proof_of_complete_coverage(self):
        d = fixture()
        d["games"] = 2
        result = MOD.audit(d)
        self.assertEqual(result["declared_scheduled_games"], 2)
        self.assertFalse(result["cohort_coverage_verified"])

    def test_post_tip_same_day_build_rejected(self):
        d = fixture()
        d["built_at_utc"] = d["predictions"][0]["logged_at_utc"] = "2026-10-28T23:01:00Z"
        with self.assertRaisesRegex(ValueError, "before tip"):
            MOD.audit(d)

    def test_log_after_tip_rejected(self):
        d = fixture()
        d["predictions"][0]["logged_at_utc"] = "2026-10-28T23:01:00Z"
        with self.assertRaisesRegex(ValueError, "before tip"):
            MOD.audit(d)

    def test_duplicate_event_player_mechanism_rejected(self):
        d = fixture()
        d["predictions"].append(copy.deepcopy(d["predictions"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            MOD.audit(d)

    def test_conflicting_event_tip_rejected(self):
        d = fixture()
        e = copy.deepcopy(d["predictions"][0]); e["player"] = "Another Player"
        e["tip_utc"] = "2026-10-29T00:00:00Z"
        d["predictions"].append(e)
        with self.assertRaisesRegex(ValueError, "conflict"):
            MOD.audit(d)

    def test_wrong_direction_rejected(self):
        d = fixture(); d["predictions"][0]["direction"] = "UP"
        with self.assertRaisesRegex(ValueError, "mechanism/direction"):
            MOD.audit(d)

    def test_nonfinite_bank_rejected(self):
        d = fixture(); d["predictions"][0]["banked_pts_pg"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            MOD.audit(d)

    def test_postgame_grade_in_frozen_log_rejected(self):
        d = fixture(); d["predictions"][0]["grade"] = "HIT"
        with self.assertRaisesRegex(ValueError, "grade"):
            MOD.audit(d)

    def test_strict_json_rejects_duplicate_keys(self):
        import json
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            json.loads('{"frozen":true,"frozen":false}', object_pairs_hook=MOD._unique_pairs)

    def test_strict_json_rejects_nan(self):
        import json
        with self.assertRaisesRegex(ValueError, "nonstandard JSON"):
            json.loads('{"pts":NaN}', parse_constant=MOD._reject_constant)


if __name__ == "__main__":
    unittest.main()
