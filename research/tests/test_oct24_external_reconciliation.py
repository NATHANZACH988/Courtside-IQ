"""Offline arithmetic and fail-closed labeling checks for Oct 24 box-score reconciliation.

These tests validate the published reconciliation manifest's structure only.
They do NOT independently authenticate ESPN, watcher notes, or predictions.
"""
import json
import unittest
from pathlib import Path


REPORT = Path(__file__).resolve().parents[1] / "verification" / "oct24_external_reconciliation.json"


class Oct24ExternalReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_original_denominator_and_event_universe(self):
        doc = self.data
        self.assertEqual(doc["frozen_manifest"]["predictions"], 53)
        self.assertEqual(doc["frozen_manifest"]["events"], 8)
        self.assertEqual(len(set(doc["external_final_stats"]["event_ids"])), 8)
        self.assertEqual(sum(v["declared"] for v in doc["outcomes"].values()), 53)
        self.assertEqual(doc["frozen_manifest"]["original_nonnull_grades"], 0)

    def test_mechanism_partition_is_exhaustive(self):
        v = self.data["outcomes"]
        self.assertEqual(
            v["FOUL_CAP"]["numeric_hit"]
            + v["FOUL_CAP"]["no_decision"]
            + v["FOUL_CAP"]["requires_watcher_notes"],
            v["FOUL_CAP"]["declared"],
        )
        self.assertEqual(
            v["CANNIBAL"]["proxy_hit"] + v["CANNIBAL"]["proxy_miss"],
            v["CANNIBAL"]["declared"],
        )
        self.assertEqual(
            v["VICTIM"]["numeric_hit"] + v["VICTIM"]["proxy_hit"]
            + v["VICTIM"]["proxy_miss"],
            v["VICTIM"]["declared"],
        )
        self.assertEqual(v["STEADY"]["numeric_miss"], v["STEADY"]["declared"])

    def test_reported_aggregate_is_not_misrepresented_as_verified(self):
        doc = self.data
        reported = doc["pax_reported"]
        self.assertEqual(
            reported["hit"] + reported["miss"] + reported["no_decision"],
            doc["frozen_manifest"]["predictions"],
        )
        self.assertFalse(reported["independently_reproduced"])
        self.assertFalse(doc["independently_verified"])
        self.assertFalse(doc["production_scoring_authorized"])
        self.assertTrue(doc["research_only"])
        self.assertFalse(doc["external_final_stats"]["original_watcher_notes_available"])
        self.assertFalse(doc["external_final_stats"]["source_is_immutable_pregame_archive"])

    def test_ticket_control_denominator_and_cold_gap_remain_visible(self):
        t = self.data["ticket_study"]
        self.assertEqual(
            t["v1_strategy_rows_total"] + t["v1_anti_control_legs"],
            t["v1_rows_total_including_control"],
        )
        self.assertEqual(t["v1_reported_total_legs"], t["v1_strategy_rows_total"])
        self.assertNotEqual(
            t["cold_losses_v1_named_categories"], t["cold_losses_v2_decomposition"]
        )
        self.assertFalse(t["cohort_definitions_reconciled"])


if __name__ == "__main__":
    unittest.main()
