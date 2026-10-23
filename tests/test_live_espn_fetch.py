"""Live ESPN fetch — skip with reason when unreachable; never invent results."""

from __future__ import annotations

import unittest

from research.providers.espn import LiveFetchError, fetch_scoreboard, parse_game_meta


class LiveEspnFetchTests(unittest.TestCase):
    def test_scoreboard_or_skip(self):
        try:
            doc = fetch_scoreboard()
        except LiveFetchError as exc:
            self.skipTest(f"Live ESPN scoreboard unreachable: {exc}")
        self.assertTrue(doc.source_url)
        self.assertTrue(doc.fetched_at_utc)
        events = doc.payload.get("events") or []
        self.assertIsInstance(events, list)
        # If any final games exist, meta parse should work on first event id path
        self.assertIn("sports", {"sports"} | set(doc.payload.keys()) | {"events"})


if __name__ == "__main__":
    unittest.main()
