"""Website prototype smoke checks."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


class WebPrototypeTests(unittest.TestCase):
    def test_required_files_exist(self):
        for name in ("index.html", "styles.css", "app.js"):
            self.assertTrue((WEB / name).exists(), name)

    def test_no_prize_and_beta_labeling(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("no prizes", html.lower())
        self.assertIn("beta", html.lower())
        self.assertIn("Courtside IQ", html)

    def test_league_first_sections(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        for needle in ("Tonight", "Leaderboard", "league", "Predict"):
            self.assertIn(needle.lower(), html.lower())

    def test_accessible_controls(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        js = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn("<label", html.lower())
        self.assertIn('type="number"', js)
        self.assertIn("<label for=", js)


if __name__ == "__main__":
    unittest.main()
