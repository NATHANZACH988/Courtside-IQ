"""Synthetic regression tests for offline NBA summary capture-loss auditing."""
import copy
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "capture" / "nba_summary_capture_audit.py"
SPEC = importlib.util.spec_from_file_location("nba_summary_capture_audit", MODULE)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def source():
    return {
        "header": {"id": "nba-test-1"},
        "officials": [{"id": "official-1"}],
        "plays": [
            {"id": "p1", "clock": {"displayValue": "11:40"},
             "coordinate": {"x": 14, "y": 7}},
            {"id": "p2", "clock": {"displayValue": "11:10"}},
        ],
        "boxscore": {
            "teams": [{"team": {"abbreviation": "AAA"},
                       "statistics": [{"name": "assists", "displayValue": "20"}]}],
            "players": [{
                "team": {"abbreviation": "AAA"},
                "statistics": [{
                    "labels": ["PTS", "AST", "3PT", "STL", "BLK", "TO", "FT"],
                    "athletes": [{
                        "athlete": {"displayName": "Sample Player"},
                        "stats": ["20", "5", "2-6", "1", "0", "3", "4-5"],
                    }],
                }],
            }],
        },
    }


def complete_capture(raw):
    return {
        "event": "nba-test-1",
        "officials": copy.deepcopy(raw["officials"]),
        "plays": copy.deepcopy(raw["plays"]),
        "team_stats": copy.deepcopy(raw["boxscore"]["teams"]),
        "players": [{
            "team": "AAA", "name": "Sample Player",
            "pts": 20, "ast": 5, "threes": 2, "three_attempts": 6,
            "stl": 1, "blk": 0, "to": 3, "ftm": 4, "fta": 5,
        }],
    }


class TestCaptureLossAudit(unittest.TestCase):
    def test_watcher_style_compaction_discards_existing_feed(self):
        raw = source()
        compact = {"event": "nba-test-1",
                   "players": [{"team": "AAA", "name": "Sample Player", "pts": 20}]}
        result = AUDIT.audit_nba_summary_capture(raw, compact)
        self.assertIn("play_by_play", result["lost_or_unreconciled"])
        self.assertIn("officials", result["lost_or_unreconciled"])
        self.assertIn("team_statistics", result["lost_or_unreconciled"])
        self.assertIn("player_ast", result["lost_or_unreconciled"])
        self.assertIn("player_3pt", result["lost_or_unreconciled"])
        self.assertFalse(result["available_fields_structurally_retained"])

    def test_complete_supplied_copy_retains_available_fields(self):
        raw = source()
        result = AUDIT.audit_nba_summary_capture(raw, complete_capture(raw))
        self.assertEqual(result["lost_or_unreconciled"], [])
        self.assertEqual(result["not_in_source"], [])
        self.assertTrue(result["available_fields_structurally_retained"])
        self.assertTrue(result["complete_source_surface_observed"])
        self.assertFalse(result["source_authenticity_verified"])
        self.assertFalse(result["player_prop_scoring_authorized"])

    def test_officials_fallback_when_top_level_is_empty(self):
        raw = source()
        raw["officials"] = []
        raw["header"]["competitions"] = [{"officials": [{"id": "ref-2"}]}]
        captured = complete_capture(raw)
        captured["officials"] = [{"id": "ref-2"}]
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["officials"]["status"], "retained")

    def test_missing_source_field_is_not_called_discarded(self):
        raw = source()
        captured = complete_capture(raw)
        raw.pop("officials")
        raw["plays"] = [{"id": "p2"}]
        captured["officials"] = []
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["officials"]["status"], "not_in_source")
        self.assertEqual(result["sections"]["play_clocks"]["status"], "not_in_source")
        self.assertFalse(result["complete_source_surface_observed"])

    def test_partial_play_by_play(self):
        raw = source()
        captured = complete_capture(raw)
        captured["plays"] = captured["plays"][:1]
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["play_by_play"]["status"], "partial")
        self.assertEqual(result["sections"]["play_clocks"]["status"], "partial")

    def test_equal_play_count_but_different_content_not_retained(self):
        raw = source()
        captured = complete_capture(raw)
        captured["plays"][0]["id"] = "fabricated"
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["play_by_play"]["status"],
                         "altered_or_unreconciled")

    def test_missing_coordinates_detected_even_when_plays_exist(self):
        raw = source()
        captured = complete_capture(raw)
        captured["plays"][0].pop("coordinate")
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["shot_coordinates"]["status"], "discarded")

    def test_incorrect_stat_value_is_not_preserved(self):
        raw = source()
        captured = complete_capture(raw)
        captured["players"][0]["ast"] = 6
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["player_ast"]["status"], "discarded")

    def test_threes_require_makes_and_attempts(self):
        raw = source()
        captured = complete_capture(raw)
        captured["players"][0].pop("three_attempts")
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["player_3pt"]["status"], "discarded")

    def test_zero_is_a_valid_captured_stat(self):
        raw = source()
        result = AUDIT.audit_nba_summary_capture(raw, complete_capture(raw))
        self.assertEqual(result["sections"]["player_blk"]["status"], "retained")

    def test_missing_player_is_not_silently_accepted(self):
        raw = source()
        captured = complete_capture(raw)
        captured["players"] = []
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["player_ast"]["status"], "discarded")

    def test_reject_mismatched_event(self):
        with self.assertRaisesRegex(ValueError, "event identity"):
            AUDIT.audit_nba_summary_capture(source(), {"event": "wrong"})

    def test_reject_duplicate_player_identity(self):
        raw = source()
        captured = complete_capture(raw)
        captured["players"].append(dict(captured["players"][0]))
        with self.assertRaisesRegex(ValueError, "ambiguous captured"):
            AUDIT.audit_nba_summary_capture(raw, captured)

    def test_reject_invalid_input_types(self):
        with self.assertRaises(TypeError):
            AUDIT.audit_nba_summary_capture([], {})
        with self.assertRaises(TypeError):
            AUDIT.audit_nba_summary_capture({}, None)

    def test_canonical_digest_does_not_claim_source_authenticity(self):
        raw = source()
        result = AUDIT.audit_nba_summary_capture(raw, complete_capture(raw))
        self.assertEqual(len(result["canonical_supplied_source_sha256"]), 64)
        self.assertFalse(result["source_authenticity_verified"])
        changed = copy.deepcopy(raw)
        changed["plays"][0]["id"] = "different"
        result2 = AUDIT.audit_nba_summary_capture(changed, complete_capture(changed))
        self.assertNotEqual(result["canonical_supplied_source_sha256"],
                            result2["canonical_supplied_source_sha256"])


if __name__ == "__main__":
    unittest.main()
