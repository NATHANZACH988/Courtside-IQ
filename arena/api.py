"""Minimal stdlib JSON HTTP API for the Prediction Arena beta."""

from __future__ import annotations

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlparse

from arena.db import Database
from arena.errors import ArenaError, ForbiddenError
from arena.service import ArenaService


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def make_handler(service: ArenaService, static_root: str | None = None) -> type:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # quieter tests
            return

        def _auth(self):
            auth = self.headers.get("Authorization", "")
            token = None
            if auth.lower().startswith("bearer "):
                token = auth[7:].strip()
            return service.user_from_token(token)

        def _ok(self, data, status: int = 200) -> None:
            json_response(self, status, {"ok": True, "data": data})

        def _err(self, exc: ArenaError) -> None:
            json_response(
                self,
                exc.http_status,
                {"ok": False, "error": {"code": exc.code, "message": exc.message}},
            )

        def do_GET(self) -> None:  # noqa: N802
            try:
                self._dispatch("GET")
            except ArenaError as exc:
                self._err(exc)
            except FileNotFoundError:
                json_response(
                    self, 404, {"ok": False, "error": {"code": "NOT_FOUND", "message": "Not found"}}
                )

        def do_POST(self) -> None:  # noqa: N802
            try:
                self._dispatch("POST")
            except ArenaError as exc:
                self._err(exc)

        def _dispatch(self, method: str) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            parts = [p for p in path.split("/") if p]

            if method == "GET" and path == "/api/health":
                self._ok({"status": "ok", "service": "courtside-iq-arena"})
                return

            if method == "POST" and path == "/api/auth/demo-login":
                # This is intentionally NOT authentication. Opt in only for local demos.
                # Never expose the display-name login on an internet-facing server.
                if (
                    os.environ.get("COURTSIDE_IQ_ALLOW_INSECURE_DEMO_LOGIN") != "1"
                    or self.client_address[0] not in ("127.0.0.1", "::1")
                ):
                    raise ForbiddenError("Insecure demo login is disabled")
                body = read_json(self)
                self._ok(service.demo_login(body.get("display_name", "")))
                return

            if method == "GET" and path == "/api/me/leagues":
                user = self._auth()
                self._ok(service.list_leagues_for_user(user))
                return

            if method == "POST" and path == "/api/leagues":
                user = self._auth()
                body = read_json(self)
                self._ok(service.create_league(user, body.get("name", "")), 201)
                return

            if method == "POST" and path == "/api/leagues/join":
                user = self._auth()
                body = read_json(self)
                self._ok(service.join_league(user, body.get("invite_code", "")))
                return

            if len(parts) == 3 and parts[0] == "api" and parts[1] == "leagues" and method == "GET":
                user = self._auth()
                self._ok(service.get_league(parts[2], viewer=user))
                return

            if (
                len(parts) == 4
                and parts[0] == "api"
                and parts[1] == "leagues"
                and parts[3] == "slates"
                and method == "POST"
            ):
                user = self._auth()
                body = read_json(self)
                self._ok(
                    service.create_slate(
                        user,
                        parts[2],
                        date_utc=body["date_utc"],
                        questions=body["questions"],
                        scoring_version=body.get("scoring_version", "closeness-v1"),
                    ),
                    201,
                )
                return

            if (
                len(parts) == 5
                and parts[0] == "api"
                and parts[1] == "leagues"
                and parts[3] == "slates"
                and parts[4] == "current"
                and method == "GET"
            ):
                user = self._auth()
                self._ok(service.current_slate(parts[2], user))
                return

            if (
                len(parts) == 4
                and parts[0] == "api"
                and parts[1] == "leagues"
                and parts[3] == "leaderboard"
                and method == "GET"
            ):
                user = self._auth()
                qs = parse_qs(parsed.query)
                window = (qs.get("window") or ["slate"])[0]
                slate_id = (qs.get("slate_id") or [None])[0]
                self._ok(service.leaderboard(parts[2], user, window=window, slate_id=slate_id))
                return

            if (
                len(parts) == 4
                and parts[0] == "api"
                and parts[1] == "questions"
                and parts[3] == "forecasts"
                and method == "POST"
            ):
                user = self._auth()
                body = read_json(self)
                self._ok(
                    service.submit_forecast(
                        user,
                        parts[2],
                        float(body["predicted_value"]),
                        client_request_id=body.get("client_request_id"),
                    ),
                    201,
                )
                return

            if (
                len(parts) == 4
                and parts[0] == "api"
                and parts[1] == "questions"
                and parts[3] == "results"
                and method == "POST"
            ):
                user = self._auth()
                body = read_json(self)
                self._ok(
                    service.ingest_result(
                        user,
                        parts[2],
                        actual_value=float(body["actual_value"]),
                        source_url=body["source_url"],
                        fetched_at_utc=body["fetched_at_utc"],
                        source_updated_at_utc=body.get("source_updated_at_utc"),
                        fixture_id=body.get("fixture_id"),
                        status=body.get("status", "official"),
                    ),
                    201,
                )
                return

            if (
                len(parts) == 4
                and parts[0] == "api"
                and parts[1] == "questions"
                and parts[3] == "void"
                and method == "POST"
            ):
                user = self._auth()
                body = read_json(self)
                self._ok(service.void_question(user, parts[2], body.get("reason", "")))
                return

            if (
                len(parts) == 4
                and parts[0] == "api"
                and parts[1] == "questions"
                and parts[3] == "corrections"
                and method == "POST"
            ):
                user = self._auth()
                body = read_json(self)
                self._ok(
                    service.correct_forecast(
                        user,
                        parts[2],
                        body["user_id"],
                        float(body["predicted_value"]),
                        body.get("reason", ""),
                    )
                )
                return

            if (
                len(parts) == 4
                and parts[0] == "api"
                and parts[1] == "questions"
                and parts[3] == "audit"
                and method == "GET"
            ):
                user = self._auth()
                self._ok(service.audit_for_question(user, parts[2]))
                return

            if (
                len(parts) == 4
                and parts[0] == "api"
                and parts[1] == "slates"
                and parts[3] == "grade"
                and method == "POST"
            ):
                user = self._auth()
                self._ok(service.grade_slate(user, parts[2]))
                return

            if method == "POST" and path == "/api/admin/lock-due":
                # Explicit privileged cron action: never mutate state through GET.
                # Fail closed until a sufficiently strong secret is configured.
                expected = os.environ.get("COURTSIDE_IQ_ADMIN_TOKEN", "")
                provided = self.headers.get("X-Courtside-IQ-Admin-Token", "")
                if len(expected) < 32 or not hmac.compare_digest(provided, expected):
                    raise ForbiddenError("Admin authorization required")
                count = service.lock_due_questions()
                self._ok({"locked": count})
                return

            if method == "GET" and path == "/api/research/tonight":
                # Live scoreboard snapshot with provenance (skip-safe for clients)
                try:
                    from research.providers.espn import fetch_scoreboard

                    doc = fetch_scoreboard()
                    games = []
                    for ev in doc.payload.get("events") or []:
                        comp = (ev.get("competitions") or [{}])[0]
                        status = (comp.get("status") or {}).get("type") or {}
                        teams = comp.get("competitors") or []
                        games.append(
                            {
                                "event_id": ev.get("id"),
                                "name": ev.get("name"),
                                "short_name": ev.get("shortName"),
                                "status": status.get("description"),
                                "completed": bool(status.get("completed")),
                                "detail": status.get("detail"),
                                "teams": [
                                    {
                                        "abbr": (t.get("team") or {}).get("abbreviation"),
                                        "score": t.get("score"),
                                        "homeAway": t.get("homeAway"),
                                    }
                                    for t in teams
                                ],
                            }
                        )
                    self._ok(
                        {
                            "source_url": doc.source_url,
                            "fetched_at_utc": doc.fetched_at_utc,
                            "games": games,
                            "rights_note": "Public ESPN JSON for beta research; commercial rights unverified.",
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    self._ok(
                        {
                            "skipped": True,
                            "reason": str(exc),
                            "games": [],
                        }
                    )
                return

            if method == "GET" and path.startswith("/api/research/coaching/"):
                event_id = parts[-1] if parts else ""
                from pathlib import Path

                path_file = (
                    Path(__file__).resolve().parents[1]
                    / "fixtures"
                    / "box_scores"
                    / "live_captures"
                    / f"{event_id}.coaching.json"
                )
                if not path_file.exists():
                    raise FileNotFoundError
                import json as _json

                self._ok(_json.loads(path_file.read_text(encoding="utf-8")))
                return

            # Static web (optional)
            if method == "GET" and static_root:
                from pathlib import Path

                root = Path(static_root)
                rel = path.lstrip("/") or "index.html"
                if ".." in rel:
                    raise FileNotFoundError
                target = root / rel
                if target.is_dir():
                    target = target / "index.html"
                if not target.exists():
                    raise FileNotFoundError
                data = target.read_bytes()
                ctype = "text/html; charset=utf-8"
                if target.suffix == ".css":
                    ctype = "text/css; charset=utf-8"
                elif target.suffix == ".js":
                    ctype = "application/javascript; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            raise FileNotFoundError

    return Handler


def create_app(db_path: str = ":memory:", static_root: str | None = None) -> tuple[ArenaService, type]:
    db = Database(db_path)
    service = ArenaService(db)
    return service, make_handler(service, static_root=static_root)


def serve(host: str = "127.0.0.1", port: int = 8080, db_path: str = "arena.db", static_root: str = "web") -> None:
    service, handler = create_app(db_path=db_path, static_root=static_root)
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"Courtside IQ Arena listening on http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    serve()
