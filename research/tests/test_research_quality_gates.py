"""Fixture-only research process audit tests; no real-world accuracy claims."""
import copy
from datetime import datetime, timezone
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from research.quality.gates import audit_manifest


DIGEST = "a" * 64


def good_manifest(sport="NFL"):
    return {
        "schema_version": 1,
        "study_id": "study:role-001",
        "sport": sport,
        "hypothesis": "Larger role increases expected opportunities",
        "sources": [
            {
                "source_id": "provider:feed-001",
                "url": "https://example.org/feed?date=2026-10-25",
                "published_at_utc": "2026-10-25T14:00:00Z",
                "captured_at_utc": "2026-10-25T14:01:00Z",
                "raw_sha256": DIGEST,
                "rights_status": "unverified",
            }
        ],
        "freeze": {
            "event_id": sport.lower() + ":game-001",
            "as_of_utc": "2026-10-25T14:05:00+00:00",
            "event_start_utc": "2026-10-25T18:00:00+00:00",
            "artifact_sha256": DIGEST,
        },
        "coverage": {
            "eligible": 20, "screened": 17,
            "excluded": 1, "unresolved": 2,
            "rejection_reasons_recorded": True,
        },
        "evaluation": {
            "frozen_predictions": 10, "graded": 9, "voided": 1,
            "pending": 0, "holdout_events": 2,
            "report_sha256": DIGEST,
            "protocol_sha256": DIGEST,
            "protocol_frozen_at_utc": "2026-10-25T14:04:00Z",
            "report_generated_at_utc": "2026-10-26T02:00:00Z",
        }
    }


class ResearchGateTests(unittest.TestCase):
    def test_complete_manifest_still_cannot_authorize_production(self):
        audit = audit_manifest(good_manifest())
        self.assertTrue(audit.source_structure_complete)
        self.assertTrue(audit.prospective_record_complete)
        self.assertTrue(audit.evaluation_record_complete)
        self.assertFalse(audit.production_authorized)
        self.assertIn("data_rights", audit.independent_reviews_required)

    def test_other_sports_are_not_forced_into_nba_fields(self):
        for sport in ("NBA", "NFL", "MLB", "NHL", "SOCCER"):
            with self.subTest(sport=sport):
                self.assertTrue(audit_manifest(good_manifest(sport)).prospective_record_complete)

    def test_missing_and_malformed_document(self):
        self.assertIn("manifest_not_object", audit_manifest([]).reasons)
        bad = good_manifest()
        bad["schema_version"] = True
        self.assertFalse(audit_manifest(bad).source_structure_complete)

    def test_unstable_study_id_rejected(self):
        bad = good_manifest()
        bad["study_id"] = "Player Name"
        self.assertIn("study_id_not_stable", audit_manifest(bad).reasons)

    def test_blank_sources_fail_closed(self):
        bad = good_manifest()
        bad["sources"] = []
        self.assertFalse(audit_manifest(bad).source_structure_complete)

    def test_malformed_source_not_crash(self):
        bad = good_manifest()
        bad["sources"][0] = ["oops"]
        self.assertFalse(audit_manifest(bad).source_structure_complete)

    def test_bad_url_credentials_and_digest(self):
        bad = good_manifest()
        bad["sources"][0]["url"] = "https://secret:password@example.org/data"
        bad["sources"][0]["raw_sha256"] = "not-a-hash"
        audit = audit_manifest(bad)
        self.assertIn("source_0_url_invalid", audit.reasons)
        self.assertIn("source_0_raw_digest_missing", audit.reasons)

    def test_duplicate_source_identity(self):
        bad = good_manifest()
        bad["sources"].append(copy.deepcopy(bad["sources"][0]))
        self.assertIn("source_1_duplicate_id", audit_manifest(bad).reasons)

    def test_missing_rights_status(self):
        bad = good_manifest()
        bad["sources"][0]["rights_status"] = "assumed"
        self.assertIn("source_0_rights_status_missing", audit_manifest(bad).reasons)

    def test_published_after_capture_invalid(self):
        bad = good_manifest()
        bad["sources"][0]["published_at_utc"] = "2026-10-25T14:02:00Z"
        self.assertIn("source_0_published_after_capture", audit_manifest(bad).reasons)

    def test_naive_datetime_invalid(self):
        bad = good_manifest()
        bad["sources"][0]["captured_at_utc"] = "2026-10-25T14:01:00"
        self.assertIn("source_0_timestamps_invalid", audit_manifest(bad).reasons)

    def test_post_cutoff_source_never_enters_prospective(self):
        bad = good_manifest()
        bad["sources"][0]["captured_at_utc"] = "2026-10-25T14:06:00Z"
        audit = audit_manifest(bad)
        self.assertTrue(audit.source_structure_complete)
        self.assertFalse(audit.prospective_record_complete)
        self.assertIn("freeze_uses_future_source", audit.reasons)

    def test_pregame_lock_at_tip_is_invalid(self):
        bad = good_manifest()
        bad["freeze"]["as_of_utc"] = bad["freeze"]["event_start_utc"]
        self.assertIn("freeze_not_before_event", audit_manifest(bad).reasons)

    def test_event_identity_matches_sport(self):
        bad = good_manifest()
        bad["freeze"]["event_id"] = "nba:game-001"
        self.assertIn("freeze_event_id_invalid", audit_manifest(bad).reasons)

    def test_full_roster_coverage_must_reconcile(self):
        bad = good_manifest()
        bad["coverage"]["screened"] = 16
        self.assertIn("coverage_does_not_reconcile", audit_manifest(bad).reasons)

    def test_coverage_requires_rejection_ledger(self):
        bad = good_manifest()
        bad["coverage"]["rejection_reasons_recorded"] = False
        self.assertIn("rejection_ledger_missing", audit_manifest(bad).reasons)

    def test_unresolved_are_retained_not_silently_screened(self):
        self.assertTrue(audit_manifest(good_manifest()).prospective_record_complete)
        self.assertEqual(good_manifest()["coverage"]["unresolved"], 2)

    def test_evaluation_denominator_must_reconcile(self):
        bad = good_manifest()
        bad["evaluation"]["graded"] = 8
        audit = audit_manifest(bad)
        self.assertTrue(audit.prospective_record_complete)
        self.assertFalse(audit.evaluation_record_complete)
        self.assertIn("evaluation_denominator_mismatch", audit.reasons)

    def test_pending_does_not_count_as_completed(self):
        bad = good_manifest()
        bad["evaluation"]["graded"] = 8
        bad["evaluation"]["pending"] = 1
        self.assertIn("evaluation_still_pending", audit_manifest(bad).reasons)

    def test_backtest_protocol_must_be_prefrozen(self):
        bad = good_manifest()
        bad["evaluation"]["protocol_frozen_at_utc"] = "2026-10-25T15:00:00Z"
        self.assertIn("evaluation_protocol_not_prefrozen", audit_manifest(bad).reasons)

    def test_report_cannot_precede_event(self):
        bad = good_manifest()
        bad["evaluation"]["report_generated_at_utc"] = "2026-10-25T15:00:00Z"
        self.assertIn("evaluation_report_before_event", audit_manifest(bad).reasons)

    def test_counts_must_be_integers_not_bools(self):
        bad = good_manifest()
        bad["evaluation"]["frozen_predictions"] = True
        self.assertIn("evaluation_counts_invalid", audit_manifest(bad).reasons)

    def test_missing_evaluation_does_not_block_prospective(self):
        bad = good_manifest()
        bad.pop("evaluation")
        audit = audit_manifest(bad)
        self.assertTrue(audit.prospective_record_complete)
        self.assertFalse(audit.evaluation_record_complete)

    def test_cli_exits_nonzero_on_future_information(self):
        bad = good_manifest()
        bad["sources"][0]["captured_at_utc"] = "2026-10-25T14:07:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "case.json"
            file.write_text(json.dumps(bad), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "research.quality.gates", str(file), "prospective"],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("freeze_uses_future_source", result.stdout)

    def test_malformed_rights_type_fails_cleanly(self):
        bad = good_manifest()
        bad["sources"][0]["rights_status"] = ["licensed"]
        audit = audit_manifest(bad)
        self.assertIn("source_0_rights_status_missing", audit.reasons)


if __name__ == "__main__":
    unittest.main()
