"""Coaching PBP + rotation baseline tests using captured live fixture when present."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "fixtures" / "box_scores" / "live_captures" / "401909848.coaching.json"
RAW = ROOT / "fixtures" / "box_scores" / "live_captures" / "401909848.json"

from research.coaching.pbp import extract_substitutions
from research.coaching.rotations import leave_one_out_accuracy, predict_replacements
from research.coaching.schemas import SubstitutionEvent


class CoachingSchemaTests(unittest.TestCase):
    def test_substitution_roundtrip_dict(self):
        s = SubstitutionEvent(
            game_id="g1",
            period=1,
            clock="7:49",
            team_id="CHI",
            player_in_id=None,
            player_in_name="Isaac Okoro",
            player_out_id=None,
            player_out_name="Matas Buzelis",
            score_margin=None,
            reason_hint="unknown",
            source_event_text="Isaac Okoro enters the game for Matas Buzelis",
        )
        d = s.to_dict()
        self.assertEqual(d["player_in_name"], "Isaac Okoro")
        self.assertEqual(d["verification"], "verified")


@unittest.skipUnless(CAPTURE.exists() and RAW.exists(), "live capture fixture not present")
class LiveCaptureCoachingTests(unittest.TestCase):
    def test_provenance_present(self):
        raw = json.loads(RAW.read_text(encoding="utf-8"))
        self.assertTrue(raw["source_url"])
        self.assertTrue(raw["fetched_at_utc"])
        self.assertEqual(raw["status"], "final")
        self.assertGreater(len(raw["players"]), 5)

    def test_substitutions_extracted(self):
        coaching = json.loads(CAPTURE.read_text(encoding="utf-8"))
        subs = coaching["bundle"]["substitutions"]
        self.assertGreater(len(subs), 10)
        self.assertTrue(all(s["verification"] == "verified" for s in subs))

    def test_rotation_forecast_runs(self):
        coaching = json.loads(CAPTURE.read_text(encoding="utf-8"))
        # Rebuild from stored substitution dicts
        subs = [
            SubstitutionEvent(
                game_id=s["game_id"],
                period=s["period"],
                clock=s["clock"],
                team_id=s["team_id"],
                player_in_id=s["player_in_id"],
                player_in_name=s["player_in_name"],
                player_out_id=s["player_out_id"],
                player_out_name=s["player_out_name"],
                score_margin=s["score_margin"],
                reason_hint=s["reason_hint"],
                source_event_text=s["source_event_text"],
            )
            for s in coaching["bundle"]["substitutions"]
        ]
        forecasts = predict_replacements(subs)
        self.assertTrue(forecasts)
        loo = leave_one_out_accuracy(subs)
        self.assertIsNotNone(loo["total"])


class SyntheticRotationTests(unittest.TestCase):
    def test_frequency_baseline(self):
        subs = [
            SubstitutionEvent(
                game_id="g",
                period=1,
                clock="8:00",
                team_id="BOS",
                player_in_id=None,
                player_in_name="Bench A",
                player_out_id=None,
                player_out_name="Starter X",
                score_margin=0,
                reason_hint="unknown",
                source_event_text="Bench A enters the game for Starter X",
            ),
            SubstitutionEvent(
                game_id="g",
                period=2,
                clock="8:00",
                team_id="BOS",
                player_in_id=None,
                player_in_name="Bench A",
                player_out_id=None,
                player_out_name="Starter X",
                score_margin=0,
                reason_hint="unknown",
                source_event_text="Bench A enters the game for Starter X",
            ),
            SubstitutionEvent(
                game_id="g",
                period=3,
                clock="8:00",
                team_id="BOS",
                player_in_id=None,
                player_in_name="Bench B",
                player_out_id=None,
                player_out_name="Starter X",
                score_margin=0,
                reason_hint="unknown",
                source_event_text="Bench B enters the game for Starter X",
            ),
        ]
        fc = predict_replacements(subs)[0]
        pred = fc.predictions[0]
        self.assertEqual(pred.predicted_in_name, "Bench A")
        self.assertAlmostEqual(pred.probability, 2 / 3, places=3)


if __name__ == "__main__":
    unittest.main()
