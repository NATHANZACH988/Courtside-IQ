"""Fixture-only tests for research claim evidence and supersession checks."""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from research.quality.claim_audit import audit_claims


DIGEST = "a" * 64
REV = "b" * 40


def claim(cid="study:ticket-1", *, kind="proxy_ticket", scope="descriptive"):
    return {
        "claim_id": cid,
        "claim_key": "claim:ticket-sweep",
        "dataset_id": "dataset:agency-oct24",
        "cohort_id": "cohort:two-leg-constructed",
        "method_id": "method:ticket-v1",
        "dataset_sha256": DIGEST,
        "method_sha256": DIGEST,
        "code_revision": REV,
        "reproduce_command": "python pull/ticket_archaeology.py",
        "source_url": "https://example.org/raw-data",
        "rights_status": "unverified",
        "kind": kind,
        "scope": scope,
        "status": "active",
        "numerator": 2,
        "denominator": 9,
        "sample_frame": "constructed_tickets",
        "line_kind": "proxy",
        "supersedes": [],
    }


def audit(*claims):
    return audit_claims({"schema_version": 1, "claims": list(claims)})


class ClaimAuditTests(unittest.TestCase):
    def test_proxy_study_structurally_complete_but_not_verified(self):
        report = audit(claim())
        self.assertTrue(report.structural_ready)
        self.assertFalse(report.independently_verified)
        self.assertFalse(report.scoring_eligible)

    def test_empty_manifest_fails(self):
        self.assertIn("claims_missing", audit_claims({"schema_version": 1, "claims": []}).reasons)

    def test_bad_schema_fails(self):
        self.assertIn("unsupported_claim_manifest", audit_claims({"schema_version": True, "claims": [claim()]}).reasons)

    def test_nonobject_claim_fails_without_crashing(self):
        self.assertIn("claim_0_not_object", audit("wrong").reasons)

    def test_missing_dataset_hash(self):
        c = claim()
        c["dataset_sha256"] = ""
        self.assertIn("claim_0_dataset_sha256_missing", audit(c).reasons)

    def test_missing_code_revision(self):
        c = claim()
        c["code_revision"] = "unversioned"
        self.assertIn("claim_0_code_revision_missing", audit(c).reasons)

    def test_missing_reproduction_command(self):
        c = claim()
        c["reproduce_command"] = ""
        self.assertIn("claim_0_reproduction_missing", audit(c).reasons)

    def test_source_url_must_not_have_credentials(self):
        c = claim()
        c["source_url"] = "https://secret:password@example.org/raw"
        self.assertIn("claim_0_source_url_invalid", audit(c).reasons)

    def test_rights_label_is_not_authorization(self):
        c = claim()
        c["rights_status"] = "licensed"
        self.assertTrue(audit(c).structural_ready)
        self.assertFalse(audit(c).scoring_eligible)

    def test_unhashable_rights_does_not_crash(self):
        c = claim()
        c["rights_status"] = ["licensed"]
        self.assertIn("claim_0_rights_status_invalid", audit(c).reasons)

    def test_win_fraction_cannot_exceed_total(self):
        c = claim()
        c["numerator"] = 10
        self.assertIn("claim_0_fraction_invalid", audit(c).reasons)

    def test_zero_denominator_fails(self):
        c = claim()
        c["denominator"] = 0
        self.assertIn("claim_0_fraction_invalid", audit(c).reasons)

    def test_bool_not_a_valid_count(self):
        c = claim()
        c["numerator"] = True
        self.assertIn("claim_0_fraction_invalid", audit(c).reasons)

    def test_published_winners_cannot_support_predictive_claim(self):
        c = claim(scope="predictive")
        c["sample_frame"] = "published_winners"
        self.assertIn("claim_0_winner_only_inference", audit(c).reasons)

    def test_proxy_ticket_cannot_claim_profitability(self):
        c = claim(scope="profitability")
        self.assertIn("claim_0_proxy_cannot_establish_profitability", audit(c).reasons)

    def test_proxy_ticket_requires_explicit_proxy_label(self):
        c = claim()
        c["line_kind"] = "posted"
        self.assertIn("claim_0_proxy_line_kind_missing", audit(c).reasons)

    def test_actual_ticket_requires_book_line_odds_side_period_and_rule(self):
        c = claim(kind="actual_ticket")
        self.assertIn("claim_0_posted_line_missing", audit(c).reasons)
        self.assertIn("claim_0_odds_invalid", audit(c).reasons)
        self.assertIn("claim_0_selection_side_missing", audit(c).reasons)

    def test_actual_ticket_cannot_be_captured_after_start(self):
        c = claim(kind="actual_ticket")
        c.update({
            "line_kind": "posted", "book": "testbook", "selection_side": "over",
            "market_period": "full_game", "settlement_version": "v1",
            "american_odds": -110, "line": 24.5,
            "quote_captured_at_utc": "2026-10-25T18:00:00Z",
            "event_start_utc": "2026-10-25T18:00:00Z",
        })
        self.assertIn("claim_0_quote_not_proven_pregame", audit(c).reasons)
        c["quote_captured_at_utc"] = "2026-10-25T17:00:00Z"
        self.assertTrue(audit(c).structural_ready)

    def test_prospective_claim_requires_prefrozen_forecast(self):
        c = claim(kind="prospective_forecast")
        self.assertIn("claim_0_forecast_not_prefrozen", audit(c).reasons)
        self.assertIn("claim_0_evaluation_protocol_missing", audit(c).reasons)

    def test_prospective_holdout_and_protocol(self):
        c = claim(kind="prospective_forecast")
        c.update({
            "frozen_at_utc": "2026-10-25T16:00:00Z",
            "event_start_utc": "2026-10-25T18:00:00Z",
            "frozen_artifact_sha256": DIGEST,
            "evaluation_protocol_id": "protocol:gameflow-v1",
            "protocol_frozen_at_utc": "2026-10-25T15:00:00Z",
            "holdout_events": 8,
        })
        self.assertTrue(audit(c).structural_ready)
        c["protocol_frozen_at_utc"] = "2026-10-25T17:00:00Z"
        self.assertIn("claim_0_protocol_not_prefrozen", audit(c).reasons)

    def test_same_cohort_different_numbers_require_supersession(self):
        old = claim("study:old")
        new = claim("study:new")
        new["numerator"] = 3
        self.assertTrue(any(x.startswith("unreconciled_cohort_result:")
                            for x in audit(old, new).reasons))

    def test_superseded_version_can_reconcile(self):
        old = claim("study:old")
        old["status"] = "superseded"
        new = claim("study:new")
        new["numerator"] = 3
        new["supersedes"] = ["study:old"]
        self.assertTrue(audit(old, new).structural_ready)

    def test_different_cohorts_are_not_automatically_contradictory(self):
        old = claim("study:old")
        old["cohort_id"] = "cohort:two-eligible"
        old["numerator"], old["denominator"] = 2, 2
        new = claim("study:new")
        new["cohort_id"] = "cohort:eight-eligible"
        new["numerator"], new["denominator"] = 2, 8
        self.assertTrue(audit(old, new).structural_ready)

    def test_unknown_superseded_claim_is_rejected(self):
        c = claim()
        c["supersedes"] = ["study:missing"]
        self.assertIn("study:ticket-1_unknown_superseded_claim", audit(c).reasons)

    def test_supersession_cycle_rejected(self):
        a = claim("study:a")
        b = claim("study:b")
        a["status"] = "superseded"
        b["status"] = "superseded"
        a["supersedes"] = ["study:b"]
        b["supersedes"] = ["study:a"]
        self.assertTrue(any(x.startswith("supersession_cycle:") for x in audit(a, b).reasons))

    def test_malformed_supersession_list_rejected(self):
        c = claim()
        c["supersedes"] = [["bad"]]
        self.assertIn("claim_0_supersedes_invalid", audit(c).reasons)

    def test_duplicate_claim_id_rejected(self):
        c = claim()
        self.assertIn("claim_1_id_duplicate", audit(c, copy.deepcopy(c)).reasons)

    def test_cli_nonzero_on_missing_evidence(self):
        c = claim()
        c["dataset_sha256"] = None
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "claims.json"
            path.write_text(json.dumps({"schema_version": 1, "claims": [c]}))
            result = subprocess.run(
                [sys.executable, "-m", "research.quality.claim_audit", str(path)],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("claim_0_dataset_sha256_missing", result.stdout)


if __name__ == "__main__":
    unittest.main()
