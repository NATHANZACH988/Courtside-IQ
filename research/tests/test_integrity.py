"""Regression tests for source chronology and completed-result evidence."""

import unittest

from research.integrity import utc_timestamp, validate_completed_capture


def sample_fixture():
    return {
        "game_id": "espn_test",
        "home_team_id": "MIL",
        "away_team_id": "CHI",
        "status": "final",
        "scheduled_tipoff_utc": "2026-10-23T20:00:00Z",
        "fetched_at_utc": "2026-10-23T22:53:22Z",
        "source_url": "https://example.org/summary?id=test",
        "players": [{"player_id": "p1", "PTS": 20}],
    }


class CaptureIntegrityTests(unittest.TestCase):
    def test_valid_postgame_capture(self):
        validate_completed_capture(sample_fixture())

    def test_reject_final_before_tipoff(self):
        f = sample_fixture()
        f["fetched_at_utc"] = "2026-10-23T19:59:00Z"
        with self.assertRaisesRegex(ValueError, "at/before"):
            validate_completed_capture(f)

    def test_reject_incomplete_game(self):
        f = sample_fixture()
        f["status"] = "in_progress"
        with self.assertRaisesRegex(ValueError, "status=final"):
            validate_completed_capture(f)

    def test_reject_missing_source(self):
        f = sample_fixture()
        f["source_url"] = ""
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            validate_completed_capture(f)

    def test_reject_missing_players(self):
        f = sample_fixture()
        f["players"] = []
        with self.assertRaisesRegex(ValueError, "nonempty"):
            validate_completed_capture(f)

    def test_reject_naive_timestamp(self):
        f = sample_fixture()
        f["fetched_at_utc"] = "2026-10-23T22:53:22"
        with self.assertRaisesRegex(ValueError, "UTC offset"):
            validate_completed_capture(f)

    def test_timezone_conversion(self):
        self.assertEqual(
            utc_timestamp("2026-10-23T16:00:00-04:00", "tip"),
            utc_timestamp("2026-10-23T20:00:00Z", "tip"),
        )


if __name__ == "__main__":
    unittest.main()
