"""Live NBA fetch — skip when unreachable; never invent results."""

from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.request


LIVE_URL = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"


class LiveDataSkipTests(unittest.TestCase):
    def test_live_scoreboard_or_skip(self):
        try:
            req = urllib.request.Request(
                LIVE_URL,
                headers={"User-Agent": "CourtsideIQ-BetaTest/0.1"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            self.skipTest(f"Live NBA scoreboard unreachable: {exc}")
        self.assertIn("scoreboard", payload)
        # Provenance only — do not fabricate if structure changes
        self.assertTrue(isinstance(payload["scoreboard"], dict))


if __name__ == "__main__":
    unittest.main()
