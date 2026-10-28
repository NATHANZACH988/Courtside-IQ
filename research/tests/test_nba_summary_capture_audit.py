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
                    "labels": ["PTS", "REB", "AST", "3PT", "STL", "BLK", "TO", "FT"],
                    "athletes": [{
                        "athlete": {"displayName": "Sample Player"},
                        "stats": ["20", "8", "5", "2-6", "1", "0", "3", "4-5"],
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
            "pts": 20, "reb": 8, "ast": 5, "threes": 2, "three_attempts": 6,
            "stl": 1, "blk": 0, "to": 3, "ftm": 4, "fta": 5,
        }],
    }


class TestCaptureLossAudit(unittest.TestCase):
    def test_non_object_source_team_is_not_silently_skipped(self):
        raw = source()
        raw["boxscore"]["teams"].append("malformed")
        with self.assertRaisesRegex(ValueError, "invalid source team record"):
            AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))

    def test_object_valued_source_team_stats_fail_even_if_capture_matches(self):
        raw = source()
        raw["boxscore"]["teams"][0]["statistics"] = {"assists": "20"}
        captured = complete_capture(raw)
        with self.assertRaisesRegex(ValueError, "invalid source team statistics"):
            AUDIT.audit_nba_summary_capture(raw, captured)

    def test_non_object_source_team_stat_element_fails_closed(self):
        raw = source()
        raw["boxscore"]["teams"][0]["statistics"].append("malformed")
        with self.assertRaisesRegex(ValueError, "invalid source team statistic"):
            AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))

    def test_source_team_with_stats_requires_identity(self):
        raw = source()
        raw["boxscore"]["teams"][0]["team"].pop("abbreviation")
        with self.assertRaisesRegex(ValueError, "source team identity missing"):
            AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))

    def test_empty_source_team_stats_remain_unobservable(self):
        raw = source()
        raw["boxscore"]["teams"][0]["statistics"] = []
        captured = complete_capture(raw)
        captured["team_stats"] = []
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["team_statistics"]["status"], "not_in_source")
        self.assertFalse(result["complete_source_surface_observed"])

    def test_malformed_source_plays_do_not_appear_absent(self):
        raw = source()
        raw["plays"] = {"id": "p1"}
        with self.assertRaisesRegex(ValueError, "invalid plays"):
            AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))

    def test_malformed_captured_officials_do_not_appear_discarded(self):
        raw = source()
        captured = complete_capture(raw)
        captured["officials"] = {"id": "official-1"}
        with self.assertRaisesRegex(ValueError, "invalid officials"):
            AUDIT.audit_nba_summary_capture(raw, captured)

    def test_malformed_source_team_list_fails_closed(self):
        raw = source()
        raw["boxscore"]["teams"] = {"team": "AAA"}
        with self.assertRaisesRegex(ValueError, "invalid source teams"):
            AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))

    def test_malformed_source_athlete_list_fails_closed(self):
        raw = source()
        raw["boxscore"]["players"][0]["statistics"][0]["athletes"] = {"athlete": "Sample Player"}
        with self.assertRaisesRegex(ValueError, "invalid source athletes"):
            AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))

    def test_malformed_captured_players_fails_closed(self):
        raw = source()
        captured = complete_capture(raw)
        captured["players"] = {}
        with self.assertRaisesRegex(ValueError, "invalid captured players"):
            AUDIT.audit_nba_summary_capture(raw, captured)

    def test_unparseable_present_source_points_fail_closed(self):
        raw = source()
        raw["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["stats"][0] = "unknown"
        with self.assertRaisesRegex(ValueError, "invalid source PTS stat"):
            AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))

    def test_negative_source_rebounds_fail_closed(self):
        raw = source()
        raw["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["stats"][1] = "-1"
        with self.assertRaisesRegex(ValueError, "invalid source REB stat"):
            AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))

    def test_impossible_source_three_point_pair_fails_closed(self):
        raw = source()
        raw["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["stats"][3] = "3-2"
        with self.assertRaisesRegex(ValueError, "invalid source 3PT stat"):
            AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))

    def test_invalid_source_free_throw_pair_fails_closed(self):
        raw = source()
        raw["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["stats"][7] = "bad"
        with self.assertRaisesRegex(ValueError, "invalid source FT stat"):
            AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))

    def test_genuinely_absent_source_stat_is_unobservable(self):
        raw = source()
        group = raw["boxscore"]["players"][0]["statistics"][0]
        group["labels"].pop(0)
        group["athletes"][0]["stats"].pop(0)
        captured = complete_capture(source())
        captured["players"][0].pop("pts")
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["player_pts"]["status"], "not_in_source")
        self.assertFalse(result["complete_source_surface_observed"])

    def test_captured_points_absent_from_source_are_unreconciled(self):
        raw = source()
        group = raw["boxscore"]["players"][0]["statistics"][0]
        group["labels"].pop(0)
        group["athletes"][0]["stats"].pop(0)
        result = AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))
        pts = result["sections"]["player_pts"]
        self.assertEqual(pts["source_items"], 0)
        self.assertEqual(pts["unexpected_items"], 1)
        self.assertEqual(pts["status"], "altered_or_unreconciled")
        self.assertFalse(result["available_fields_structurally_retained"])

    def test_unverified_single_three_point_component_is_unreconciled(self):
        raw = source()
        group = raw["boxscore"]["players"][0]["statistics"][0]
        group["labels"].remove("3PT")
        group["athletes"][0]["stats"].pop(3)
        captured = complete_capture(source())
        captured["players"][0].pop("three_attempts")
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        threes = result["sections"]["player_3pt"]
        self.assertEqual(threes["unexpected_items"], 1)
        self.assertEqual(threes["status"], "altered_or_unreconciled")

    def test_dnp_player_with_fabricated_points_is_unreconciled(self):
        raw = source()
        dnp = copy.deepcopy(raw["boxscore"]["players"][0]["statistics"][0]["athletes"][0])
        dnp["athlete"]["displayName"] = "DNP Player"
        dnp["didNotPlay"] = True
        dnp["stats"] = []
        raw["boxscore"]["players"][0]["statistics"][0]["athletes"].append(dnp)
        captured = complete_capture(raw)
        captured["players"].append({"team": "AAA", "name": "DNP Player", "pts": 12})
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["player_identity"]["status"], "retained")
        pts = result["sections"]["player_pts"]
        self.assertEqual(pts["unexpected_items"], 1)
        self.assertEqual(pts["status"], "altered_or_unreconciled")

    def test_mixed_player_rows_with_unverified_stat_fail_closed(self):
        raw = source()
        group = raw["boxscore"]["players"][0]["statistics"][0]
        second = copy.deepcopy(group["athletes"][0])
        second["athlete"]["displayName"] = "Second Player"
        second["stats"].pop(0)
        group["athletes"].append(second)
        # ESPN can supply different label sets in separate stat groups.
        group["athletes"].pop()
        raw["boxscore"]["players"][0]["statistics"].append({
            "labels": group["labels"][1:],
            "athletes": [second],
        })
        captured = complete_capture(source())
        extra = dict(captured["players"][0])
        extra["name"] = "Second Player"
        captured["players"].append(extra)
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        pts = result["sections"]["player_pts"]
        self.assertEqual(pts["source_items"], 1)
        self.assertEqual(pts["retained_items"], 1)
        self.assertEqual(pts["unexpected_items"], 1)
        self.assertEqual(pts["status"], "altered_or_unreconciled")
        self.assertFalse(result["available_fields_structurally_retained"])

    def test_missing_points_are_detected_even_when_other_stats_match(self):
        raw = source()
        captured = complete_capture(raw)
        captured["players"][0].pop("pts")
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["player_pts"]["status"], "discarded")
        self.assertFalse(result["available_fields_structurally_retained"])

    def test_altered_points_fail_closed(self):
        raw = source()
        captured = complete_capture(raw)
        captured["players"][0]["pts"] = 21
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["player_pts"]["status"], "altered_or_unreconciled")
        self.assertEqual(result["sections"]["player_pts"]["altered_items"], 1)

    def test_missing_rebounds_are_detected_even_when_other_stats_match(self):
        raw = source()
        captured = complete_capture(raw)
        captured["players"][0].pop("reb")
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["player_reb"]["status"], "discarded")
        self.assertFalse(result["available_fields_structurally_retained"])

    def test_altered_rebounds_fail_closed(self):
        raw = source()
        captured = complete_capture(raw)
        captured["players"][0]["reb"] = 9
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["player_reb"]["status"], "altered_or_unreconciled")
        self.assertEqual(result["sections"]["player_reb"]["altered_items"], 1)

    def test_points_and_rebounds_retain_zero_values(self):
        raw = source()
        raw["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["stats"][0] = "0"
        raw["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["stats"][1] = "0"
        captured = complete_capture(raw)
        captured["players"][0]["pts"] = 0
        captured["players"][0]["reb"] = 0
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["player_pts"]["status"], "retained")
        self.assertEqual(result["sections"]["player_reb"]["status"], "retained")

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
        # Extra captured clocks without source events are unverified, not retained.
        self.assertEqual(result["sections"]["play_clocks"]["status"],
                         "altered_or_unreconciled")
        self.assertFalse(result["complete_source_surface_observed"])

    def test_shorter_modified_officials_are_unreconciled(self):
        raw = source()
        raw["officials"].append({"id": "official-2"})
        captured = complete_capture(raw)
        captured["officials"] = [{"id": "not-in-source"}]
        section = AUDIT.audit_nba_summary_capture(raw, captured)["sections"]["officials"]
        self.assertEqual(section["status"], "altered_or_unreconciled")

    def test_shorter_modified_team_stats_are_unreconciled(self):
        raw = source()
        raw["boxscore"]["teams"].append({
            "team": {"abbreviation": "BBB"},
            "statistics": [{"name": "assists", "displayValue": "15"}],
        })
        captured = complete_capture(raw)
        captured["team_stats"] = [{
            "team": {"abbreviation": "AAA"},
            "statistics": [{"name": "assists", "displayValue": "999"}],
        }]
        section = AUDIT.audit_nba_summary_capture(raw, captured)["sections"]["team_statistics"]
        self.assertEqual(section["status"], "altered_or_unreconciled")

    def test_exact_ordered_official_subset_remains_partial(self):
        raw = source()
        raw["officials"].append({"id": "official-2"})
        captured = complete_capture(raw)
        captured["officials"] = [{"id": "official-2"}]
        section = AUDIT.audit_nba_summary_capture(raw, captured)["sections"]["officials"]
        self.assertEqual(section["status"], "partial")

    def test_exact_ordered_team_subset_remains_partial(self):
        raw = source()
        raw["boxscore"]["teams"].append({
            "team": {"abbreviation": "BBB"},
            "statistics": [{"name": "assists", "displayValue": "15"}],
        })
        captured = complete_capture(raw)
        captured["team_stats"] = captured["team_stats"][1:]
        section = AUDIT.audit_nba_summary_capture(raw, captured)["sections"]["team_statistics"]
        self.assertEqual(section["status"], "partial")

    def test_extra_official_without_source_is_unreconciled(self):
        raw = source()
        captured = complete_capture(raw)
        raw["officials"] = []
        section = AUDIT.audit_nba_summary_capture(raw, captured)["sections"]["officials"]
        self.assertEqual(section["status"], "altered_or_unreconciled")

    def test_reordered_officials_are_not_retained(self):
        raw = source()
        raw["officials"].append({"id": "official-2"})
        captured = complete_capture(raw)
        captured["officials"].reverse()
        section = AUDIT.audit_nba_summary_capture(raw, captured)["sections"]["officials"]
        self.assertEqual(section["status"], "altered_or_unreconciled")

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

    def test_fabricated_subset_play_is_not_mislabeled_partial(self):
        raw = source()
        captured = complete_capture(raw)
        captured["plays"] = [{"id": "fabricated", "clock": {"displayValue": "11:40"}}]
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["play_by_play"]["status"],
                         "altered_or_unreconciled")
        self.assertEqual(result["sections"]["play_clocks"]["status"],
                         "altered_or_unreconciled")

    def test_coordinate_moved_to_another_play_is_not_retained(self):
        raw = source()
        captured = complete_capture(raw)
        moved = captured["plays"][0].pop("coordinate")
        captured["plays"][1]["coordinate"] = moved
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["shot_coordinates"]["status"],
                         "altered_or_unreconciled")

    def test_clock_moved_to_different_play_is_not_retained(self):
        raw = source()
        captured = complete_capture(raw)
        captured["plays"][0]["clock"], captured["plays"][1]["clock"] = (
            captured["plays"][1]["clock"], captured["plays"][0]["clock"])
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["play_clocks"]["status"],
                         "altered_or_unreconciled")

    def test_duplicate_play_ids_fail_closed(self):
        raw = source()
        captured = complete_capture(raw)
        captured["plays"][1]["id"] = captured["plays"][0]["id"]
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["play_by_play"]["status"],
                         "altered_or_unreconciled")

    def test_capture_with_no_source_plays_is_unreconciled(self):
        raw = source()
        captured = complete_capture(raw)
        raw["plays"] = []
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["play_by_play"]["status"],
                         "altered_or_unreconciled")
        self.assertEqual(result["sections"]["play_clocks"]["status"],
                         "altered_or_unreconciled")
        self.assertEqual(result["sections"]["shot_coordinates"]["status"],
                         "altered_or_unreconciled")

    def test_exact_partial_play_subset_remains_partial(self):
        raw = source()
        captured = complete_capture(raw)
        captured["plays"] = [copy.deepcopy(raw["plays"][1])]
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["play_by_play"]["status"], "partial")
        self.assertEqual(result["sections"]["play_clocks"]["status"], "partial")

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
        self.assertEqual(result["sections"]["player_ast"]["status"], "altered_or_unreconciled")
        self.assertEqual(result["sections"]["player_ast"]["captured_items"], 1)
        self.assertEqual(result["sections"]["player_ast"]["altered_items"], 1)

    def test_threes_require_makes_and_attempts(self):
        raw = source()
        captured = complete_capture(raw)
        captured["players"][0].pop("three_attempts")
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["player_3pt"]["status"], "partial")
        self.assertEqual(result["sections"]["player_3pt"]["captured_items"], 1)
        self.assertEqual(result["sections"]["player_3pt"]["partial_items"], 1)

    def test_wrong_three_point_attempts_are_altered_not_missing(self):
        raw = source()
        captured = complete_capture(raw)
        captured["players"][0]["three_attempts"] = 7
        section = AUDIT.audit_nba_summary_capture(raw, captured)["sections"]["player_3pt"]
        self.assertEqual(section["status"], "altered_or_unreconciled")
        self.assertEqual(section["captured_items"], 1)
        self.assertEqual(section["altered_items"], 1)

    def test_wrong_three_makes_without_attempts_is_altered(self):
        raw = source()
        captured = complete_capture(raw)
        captured["players"][0].pop("three_attempts")
        captured["players"][0]["threes"] = 3  # Source is 2-6.
        section = AUDIT.audit_nba_summary_capture(raw, captured)["sections"]["player_3pt"]
        self.assertEqual(section["status"], "altered_or_unreconciled")
        self.assertEqual(section["altered_items"], 1)
        self.assertEqual(section["partial_items"], 0)

    def test_wrong_three_attempts_without_makes_is_altered(self):
        raw = source()
        captured = complete_capture(raw)
        captured["players"][0].pop("threes")
        captured["players"][0]["three_attempts"] = 7  # Source is 2-6.
        section = AUDIT.audit_nba_summary_capture(raw, captured)["sections"]["player_3pt"]
        self.assertEqual(section["status"], "altered_or_unreconciled")
        self.assertEqual(section["altered_items"], 1)

    def test_wrong_ft_attempts_without_makes_is_altered(self):
        raw = source()
        captured = complete_capture(raw)
        captured["players"][0].pop("ftm")
        captured["players"][0]["fta"] = 6  # Source is 4-5.
        section = AUDIT.audit_nba_summary_capture(raw, captured)["sections"]["player_ft"]
        self.assertEqual(section["status"], "altered_or_unreconciled")
        self.assertEqual(section["altered_items"], 1)

    def test_correct_partial_ft_remains_partial(self):
        raw = source()
        captured = complete_capture(raw)
        captured["players"][0].pop("fta")
        section = AUDIT.audit_nba_summary_capture(raw, captured)["sections"]["player_ft"]
        self.assertEqual(section["status"], "partial")
        self.assertEqual(section["partial_items"], 1)
        self.assertEqual(section["altered_items"], 0)

    def test_mixed_retained_and_missing_players_is_partial(self):
        raw = source()
        second = copy.deepcopy(raw["boxscore"]["players"][0]["statistics"][0]["athletes"][0])
        second["athlete"]["displayName"] = "Second Player"
        raw["boxscore"]["players"][0]["statistics"][0]["athletes"].append(second)
        captured = complete_capture(raw)
        section = AUDIT.audit_nba_summary_capture(raw, captured)["sections"]["player_ast"]
        self.assertEqual(section["source_items"], 2)
        self.assertEqual(section["captured_items"], 1)
        self.assertEqual(section["retained_items"], 1)
        self.assertEqual(section["status"], "partial")

    def test_mixed_valid_and_corrupted_players_is_altered(self):
        raw = source()
        second = copy.deepcopy(raw["boxscore"]["players"][0]["statistics"][0]["athletes"][0])
        second["athlete"]["displayName"] = "Second Player"
        raw["boxscore"]["players"][0]["statistics"][0]["athletes"].append(second)
        captured = complete_capture(raw)
        captured["players"].append({
            "team": "AAA", "name": "Second Player", "ast": 9,
        })
        section = AUDIT.audit_nba_summary_capture(raw, captured)["sections"]["player_ast"]
        self.assertEqual(section["source_items"], 2)
        self.assertEqual(section["captured_items"], 2)
        self.assertEqual(section["retained_items"], 1)
        self.assertEqual(section["altered_items"], 1)
        self.assertEqual(section["status"], "altered_or_unreconciled")

    def test_invalid_present_stat_is_altered(self):
        raw = source()
        captured = complete_capture(raw)
        captured["players"][0]["ast"] = "not-a-number"
        section = AUDIT.audit_nba_summary_capture(raw, captured)["sections"]["player_ast"]
        self.assertEqual(section["status"], "altered_or_unreconciled")
        self.assertEqual(section["altered_items"], 1)

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

    def test_unexpected_captured_player_cannot_pass_as_retained(self):
        raw = source()
        captured = complete_capture(raw)
        fabricated = dict(captured["players"][0])
        fabricated["name"] = "Fabricated Player"
        captured["players"].append(fabricated)
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        identity = result["sections"]["player_identity"]
        self.assertEqual(identity["status"], "altered_or_unreconciled")
        self.assertEqual(identity["unexpected_items"], 1)
        self.assertIn("player_identity", result["lost_or_unreconciled"])
        self.assertFalse(result["available_fields_structurally_retained"])
        # Matching original stats do not excuse an invented extra athlete.
        self.assertEqual(result["sections"]["player_ast"]["status"], "retained")

    def test_missing_captured_player_is_partial_identity_coverage(self):
        raw = source()
        second = copy.deepcopy(raw["boxscore"]["players"][0]["statistics"][0]["athletes"][0])
        second["athlete"]["displayName"] = "Second Player"
        raw["boxscore"]["players"][0]["statistics"][0]["athletes"].append(second)
        result = AUDIT.audit_nba_summary_capture(raw, complete_capture(raw))
        identity = result["sections"]["player_identity"]
        self.assertEqual(identity["status"], "partial")
        self.assertEqual(identity["matched_items"], 1)
        self.assertEqual(identity["missing_items"], 1)

    def test_captured_player_without_source_player_is_unreconciled(self):
        raw = source()
        raw["boxscore"]["players"] = []
        result = AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))
        self.assertEqual(result["sections"]["player_identity"]["status"],
                         "altered_or_unreconciled")
        self.assertEqual(result["sections"]["player_identity"]["unexpected_items"], 1)

    def test_no_source_or_captured_players_is_unobservable(self):
        raw = source()
        raw["boxscore"]["players"] = []
        captured = complete_capture(source())
        captured["players"] = []
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["player_identity"]["status"], "not_in_source")
        self.assertIn("player_identity", result["not_in_source"])

    def test_second_source_stat_group_is_counted_in_full_roster(self):
        raw = source()
        second = copy.deepcopy(raw["boxscore"]["players"][0]["statistics"][0])
        second["athletes"][0]["athlete"]["displayName"] = "Second Group Player"
        raw["boxscore"]["players"][0]["statistics"].append(second)
        captured = complete_capture(raw)  # Only the first group's athlete.
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        identity = result["sections"]["player_identity"]
        self.assertEqual(identity["source_items"], 2)
        self.assertEqual(identity["missing_items"], 1)
        self.assertEqual(identity["status"], "partial")
        assists = result["sections"]["player_ast"]
        self.assertEqual(assists["source_items"], 2)
        self.assertEqual(assists["status"], "partial")
        self.assertFalse(result["available_fields_structurally_retained"])

    def test_second_source_stat_group_can_be_fully_retained(self):
        raw = source()
        second = copy.deepcopy(raw["boxscore"]["players"][0]["statistics"][0])
        second["athletes"][0]["athlete"]["displayName"] = "Second Group Player"
        raw["boxscore"]["players"][0]["statistics"].append(second)
        captured = complete_capture(raw)
        extra = dict(captured["players"][0])
        extra["name"] = "Second Group Player"
        captured["players"].append(extra)
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["player_identity"]["status"], "retained")
        self.assertEqual(result["sections"]["player_ast"]["status"], "retained")
        self.assertTrue(result["available_fields_structurally_retained"])

    def test_malformed_second_stat_group_fails_closed(self):
        raw = source()
        second = copy.deepcopy(raw["boxscore"]["players"][0]["statistics"][0])
        second["athletes"][0]["athlete"]["displayName"] = "Second Group Player"
        second["athletes"][0]["stats"] = ["20"]
        raw["boxscore"]["players"][0]["statistics"].append(second)
        with self.assertRaisesRegex(ValueError, "labels/stats length mismatch"):
            AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))

    def test_duplicate_player_across_stat_groups_fails_closed(self):
        raw = source()
        raw["boxscore"]["players"][0]["statistics"].append(
            copy.deepcopy(raw["boxscore"]["players"][0]["statistics"][0]))
        with self.assertRaisesRegex(ValueError, "ambiguous source player identity"):
            AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))

    def test_source_stats_shorter_than_labels_fail_closed(self):
        raw = source()
        raw["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["stats"] = ["20", "5"]
        with self.assertRaisesRegex(ValueError, "labels/stats length mismatch"):
            AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))

    def test_source_stats_longer_than_labels_fail_closed(self):
        raw = source()
        raw["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["stats"].append("99")
        with self.assertRaisesRegex(ValueError, "labels/stats length mismatch"):
            AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))

    def test_duplicate_source_stat_labels_fail_closed(self):
        raw = source()
        labels = raw["boxscore"]["players"][0]["statistics"][0]["labels"]
        labels[3] = "AST"
        with self.assertRaisesRegex(ValueError, "duplicate source stat labels"):
            AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))

    def test_empty_stats_for_explicit_dnp_player_are_allowed(self):
        raw = source()
        dnp = copy.deepcopy(raw["boxscore"]["players"][0]["statistics"][0]["athletes"][0])
        dnp["athlete"]["displayName"] = "DNP Player"
        dnp["didNotPlay"] = True
        dnp["stats"] = []
        raw["boxscore"]["players"][0]["statistics"][0]["athletes"].append(dnp)
        captured = complete_capture(raw)
        captured["players"].append({"team": "AAA", "name": "DNP Player"})
        result = AUDIT.audit_nba_summary_capture(raw, captured)
        self.assertEqual(result["sections"]["player_identity"]["status"], "retained")
        self.assertEqual(result["sections"]["player_ast"]["status"], "retained")

    def test_empty_stats_without_dnp_marker_fail_closed(self):
        raw = source()
        raw["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["stats"] = []
        with self.assertRaisesRegex(ValueError, "labels/stats length mismatch"):
            AUDIT.audit_nba_summary_capture(raw, complete_capture(source()))

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
