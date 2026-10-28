"""Synthetic provenance and chronology regressions, not forecast backtests."""
import copy
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "provenance" / "forecast_trace.py"
SPEC = importlib.util.spec_from_file_location("forecast_trace", MODULE)
TRACE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRACE)


def fixture():
    prompt = "Evaluate all players without looking at sportsbook lines first."
    return {
        "schema": TRACE.SCHEMA,
        "prompt": {"text": prompt, "sha256": sha256(prompt.encode()).hexdigest()},
        "model": {"name": "independent-research", "version": "0.1",
                  "code_ref": "manual-research-v1", "method": "minutes x per-minute rate"},
        "event": {"id": "synthetic-event", "tipoff_utc": "2030-10-28T23:00:00Z"},
        "created_at_utc": "2030-10-28T18:00:00Z",
        "frozen_at_utc": "2030-10-28T19:00:00Z",
        "status": "research_only",
        "sources": [{"id": "s1", "url": "https://www.nba.com/",
                     "retrieved_at_utc": "2030-10-28T18:30:00Z",
                     "sha256": "a" * 64, "input_or_claim": "synthetic minute estimate"}],
        "candidates": [{"player_id": "player-1", "team_id": "team-1", "stat": "PTS",
                        "mean": 24, "range": [20, 28], "calculation": "32 min * 0.75 PTS/min",
                        "source_ids": ["s1"], "decision": "consider", "reason": "research"}],
        "quotes": [{"id": "q1", "player_id": "player-1", "stat": "PTS",
                    "sportsbook": "synthetic", "url": "https://www.nba.com/",
                    "kind": "range", "lower": 23, "upper": 25, "american_odds": 250,
                    "retrieved_at_utc": "2030-10-28T19:10:00Z"}],
    }


class TestForecastTrace(unittest.TestCase):
    def test_valid_seal_and_verify(self):
        record = TRACE.seal_trace(fixture(), now=datetime(2030, 10, 28, 19, 20, tzinfo=timezone.utc))
        self.assertEqual(TRACE.verify_receipt(record), record["trace_sha256"])
        self.assertFalse(record["external_timestamp_verified"])

    def test_prompt_edit_without_digest_fails(self):
        trace = fixture()
        trace["prompt"]["text"] += " updated"
        with self.assertRaisesRegex(ValueError, "prompt digest"):
            TRACE.validate_trace(trace)

    def test_source_after_forecast_fails(self):
        trace = fixture()
        trace["sources"][0]["retrieved_at_utc"] = "2030-10-28T19:01:00Z"
        with self.assertRaisesRegex(ValueError, "source retrieved after freeze"):
            TRACE.validate_trace(trace)

    def test_quote_before_forecast_fails(self):
        trace = fixture()
        trace["quotes"][0]["retrieved_at_utc"] = "2030-10-28T18:59:00Z"
        with self.assertRaisesRegex(ValueError, "quote must be captured"):
            TRACE.validate_trace(trace)

    def test_duplicate_candidates_fail(self):
        trace = fixture()
        trace["candidates"].append(copy.deepcopy(trace["candidates"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate player-stat"):
            TRACE.validate_trace(trace)

    def test_unknown_source_fails(self):
        trace = fixture()
        trace["candidates"][0]["source_ids"] = ["nonexistent"]
        with self.assertRaisesRegex(ValueError, "unknown/missing source"):
            TRACE.validate_trace(trace)

    def test_modified_sealed_forecast_fails(self):
        receipt = TRACE.seal_trace(fixture(), now=datetime(2030, 10, 28, 19, 20, tzinfo=timezone.utc))
        receipt["trace"]["candidates"][0]["mean"] = 25
        with self.assertRaisesRegex(ValueError, "sealed trace content changed"):
            TRACE.verify_receipt(receipt)

    def test_post_tip_seal_rejected(self):
        with self.assertRaisesRegex(ValueError, "cannot seal after tipoff"):
            TRACE.seal_trace(fixture(), now=datetime(2030, 10, 28, 23, 0, tzinfo=timezone.utc))

    def test_invalid_exact_and_nan_fail(self):
        trace = fixture()
        trace["quotes"][0].update(kind="exact", lower=24, upper=25)
        with self.assertRaisesRegex(ValueError, "quote bounds"):
            TRACE.validate_trace(trace)
        trace = fixture()
        trace["candidates"][0]["mean"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite numeric"):
            TRACE.validate_trace(trace)

    def test_reject_play_authority(self):
        trace = fixture()
        trace["status"] = "play"
        with self.assertRaisesRegex(ValueError, "research_only"):
            TRACE.validate_trace(trace)

    def test_quote_after_seal_fails(self):
        with self.assertRaisesRegex(ValueError, "before supplied market capture"):
            TRACE.seal_trace(fixture(), now=datetime(2030, 10, 28, 19, 5, tzinfo=timezone.utc))

    def test_seal_timestamp_edit_detected(self):
        receipt = TRACE.seal_trace(fixture(), now=datetime(2030, 10, 28, 19, 20, tzinfo=timezone.utc))
        receipt["sealed_at_utc"] = "2030-10-28T19:15:00+00:00"
        with self.assertRaisesRegex(ValueError, "seal metadata changed"):
            TRACE.verify_receipt(receipt)

    def test_cannot_self_attest_external_timestamp(self):
        receipt = TRACE.seal_trace(fixture(), now=datetime(2030, 10, 28, 19, 20, tzinfo=timezone.utc))
        receipt["external_timestamp_verified"] = True
        with self.assertRaisesRegex(ValueError, "cannot assert external"):
            TRACE.verify_receipt(receipt)


    def test_strict_json_accepts_normal_receipt(self):
        import json
        receipt = TRACE.seal_trace(
            fixture(), now=datetime(2030, 10, 28, 19, 20, tzinfo=timezone.utc))
        loaded = TRACE.load_strict_json(json.dumps(receipt))
        self.assertEqual(TRACE.verify_receipt(loaded), receipt["trace_sha256"])

    def test_strict_json_rejects_duplicate_top_level_receipt_keys(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON object key: trace"):
            TRACE.load_strict_json('{"trace": {}, "trace": {}}')

    def test_strict_json_rejects_duplicate_nested_projection_keys(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON object key: mean"):
            TRACE.load_strict_json('{"trace": {"candidates": [{"mean": 999, "mean": 24}]}}')

    def test_strict_json_rejects_nonstandard_nan(self):
        with self.assertRaisesRegex(ValueError, "non-finite JSON number: NaN"):
            TRACE.load_strict_json('{"mean": NaN}')

    def test_strict_json_rejects_nonstandard_infinity(self):
        with self.assertRaisesRegex(ValueError, "non-finite JSON number: Infinity"):
            TRACE.load_strict_json('{"mean": Infinity}')


if __name__ == "__main__":
    unittest.main()
