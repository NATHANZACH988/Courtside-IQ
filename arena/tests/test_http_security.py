"""HTTP regression tests for fail-closed demo and privileged cron routes."""

from __future__ import annotations

import json
import os
import threading
import unittest
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from arena.api import make_handler
from arena.db import Database
from arena.service import ArenaService


@contextmanager
def environment(**values):
    with patch.dict(os.environ, values, clear=False):
        yield


class HttpSecurityTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.service = ArenaService(self.db)
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(self.service)
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.db.close()

    def request(self, method, path, body=None, headers=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            with urlopen(req, timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def seed_due_question(self):
        owner = self.service.create_user("Cron owner")
        league = self.service.create_league(owner, "Cron league")
        slate = self.service.create_slate(
            owner,
            league["id"],
            date_utc="2024-01-15",
            questions=[{
                "game": {
                    "id": "g-cron", "season": "2023-24",
                    "home_team_id": "BOS", "away_team_id": "IND",
                    "scheduled_tipoff_utc": "2024-01-15T00:30:00Z",
                },
                "player": {
                    "id": "p-cron", "full_name": "Example Player",
                    "team_id": "BOS",
                },
                "stat": "PTS", "frozen_baseline": 20,
                "prompt_text": "Points?",
            }],
        )
        return slate["questions"][0]["id"]

    def test_demo_login_disabled_by_default(self):
        with environment(COURTSIDE_IQ_ALLOW_INSECURE_DEMO_LOGIN="0"):
            status, body = self.request(
                "POST", "/api/auth/demo-login", {"display_name": "Commissioner"}
            )
        self.assertEqual(status, 403)
        self.assertFalse(body["ok"])

    def test_explicit_local_demo_opt_in(self):
        with environment(COURTSIDE_IQ_ALLOW_INSECURE_DEMO_LOGIN="1"):
            status, body = self.request(
                "POST", "/api/auth/demo-login", {"display_name": "Local Demo"}
            )
        self.assertEqual(status, 200)
        self.assertTrue(body["data"]["token"])

    def test_get_lock_route_is_non_mutating(self):
        qid = self.seed_due_question()
        status, _ = self.request("GET", "/api/admin/lock-due")
        self.assertEqual(status, 404)
        self.assertEqual(
            self.db.fetchone("SELECT status FROM questions WHERE id = ?", (qid,))["status"],
            "open",
        )

    def test_admin_lock_requires_configured_secret(self):
        qid = self.seed_due_question()
        with environment(COURTSIDE_IQ_ADMIN_TOKEN=""):
            status, _ = self.request("POST", "/api/admin/lock-due", {})
        self.assertEqual(status, 403)
        self.assertEqual(
            self.db.fetchone("SELECT status FROM questions WHERE id = ?", (qid,))["status"],
            "open",
        )

    def test_short_or_wrong_admin_secret_is_rejected(self):
        self.seed_due_question()
        for secret, supplied in [("short", "short"), ("x" * 32, "y" * 32)]:
            with self.subTest(secret=secret):
                with environment(COURTSIDE_IQ_ADMIN_TOKEN=secret):
                    status, _ = self.request(
                        "POST", "/api/admin/lock-due", {},
                        {"X-Courtside-IQ-Admin-Token": supplied},
                    )
                self.assertEqual(status, 403)

    def test_authorized_post_locks_due_questions(self):
        qid = self.seed_due_question()
        secret = "z" * 40
        with environment(COURTSIDE_IQ_ADMIN_TOKEN=secret):
            status, body = self.request(
                "POST", "/api/admin/lock-due", {},
                {"X-Courtside-IQ-Admin-Token": secret},
            )
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["locked"], 1)
        self.assertEqual(
            self.db.fetchone("SELECT status FROM questions WHERE id = ?", (qid,))["status"],
            "locked",
        )


if __name__ == "__main__":
    unittest.main()
