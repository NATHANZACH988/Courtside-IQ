"""Prediction Arena domain service — vertical slice workflow."""

from __future__ import annotations

import secrets
import uuid
from typing import Any

from arena.db import Database, dumps, row_to_dict
from arena.errors import (
    ConflictError,
    ForbiddenError,
    LockPassedError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from arena.scoring import SCORING_VERSION, grade_prediction, is_provisional
from arena.timeutil import now_iso, parse_iso, to_iso, utc_now


HOUSE_AI_DISPLAY = "Courtside IQ AI"
BASELINE_VERSION = "season-avg-v1"


def new_id(prefix: str = "") -> str:
    uid = str(uuid.uuid4())
    return f"{prefix}{uid}" if prefix else uid


class ArenaService:
    def __init__(self, db: Database, *, clock=None) -> None:
        self.db = db
        self._clock = clock or utc_now

    def _now(self) -> str:
        return to_iso(self._clock())

    # --- auth / users -------------------------------------------------

    def create_user(
        self,
        display_name: str,
        *,
        email: str | None = None,
        is_house_ai: bool = False,
    ) -> dict:
        user_id = new_id("usr_")
        created = self._now()
        self.db.execute(
            """
            INSERT INTO users (id, display_name, email, is_house_ai, created_at_utc)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, display_name.strip(), email, 1 if is_house_ai else 0, created),
        )
        return self.get_user(user_id)

    def get_user(self, user_id: str) -> dict:
        row = self.db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
        if not row:
            raise NotFoundError("User not found")
        return row_to_dict(row)  # type: ignore[return-value]

    def demo_login(self, display_name: str) -> dict:
        """Beta-only passwordless login creating a session."""
        if not display_name or not display_name.strip():
            raise ValidationError("display_name is required")
        existing = self.db.fetchone(
            "SELECT * FROM users WHERE display_name = ? AND is_house_ai = 0",
            (display_name.strip(),),
        )
        if existing:
            user = row_to_dict(existing)
        else:
            user = self.create_user(display_name.strip())
        token = secrets.token_urlsafe(32)
        created = self._now()
        from datetime import timedelta

        expires = to_iso(self._clock() + timedelta(days=30))
        self.db.execute(
            """
            INSERT INTO sessions (token, user_id, created_at_utc, expires_at_utc)
            VALUES (?, ?, ?, ?)
            """,
            (token, user["id"], created, expires),
        )
        return {"token": token, "user": user, "expires_at_utc": expires}

    def user_from_token(self, token: str | None) -> dict:
        if not token:
            raise UnauthorizedError("Authentication required")
        row = self.db.fetchone(
            """
            SELECT u.*, s.expires_at_utc AS session_expires
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        )
        if not row:
            raise UnauthorizedError("Invalid session")
        if parse_iso(row["session_expires"]) <= self._clock():
            raise UnauthorizedError("Session expired")
        data = row_to_dict(row)
        assert data is not None
        data.pop("session_expires", None)
        return data

    def ensure_house_ai(self) -> dict:
        row = self.db.fetchone("SELECT * FROM users WHERE is_house_ai = 1 LIMIT 1")
        if row:
            return row_to_dict(row)  # type: ignore[return-value]
        return self.create_user(HOUSE_AI_DISPLAY, is_house_ai=True)

    # --- leagues ------------------------------------------------------

    def create_league(self, owner: dict, name: str) -> dict:
        if not name.strip():
            raise ValidationError("league name is required")
        league_id = new_id("lg_")
        invite = secrets.token_urlsafe(8)
        created = self._now()
        self.db.execute(
            """
            INSERT INTO leagues (id, name, owner_user_id, visibility, invite_code, created_at_utc)
            VALUES (?, ?, ?, 'invite', ?, ?)
            """,
            (league_id, name.strip(), owner["id"], invite, created),
        )
        self.db.execute(
            """
            INSERT INTO league_members (league_id, user_id, role, joined_at_utc)
            VALUES (?, ?, 'commissioner', ?)
            """,
            (league_id, owner["id"], created),
        )
        # House AI joins every league under identical rules
        ai = self.ensure_house_ai()
        self.db.execute(
            """
            INSERT INTO league_members (league_id, user_id, role, joined_at_utc)
            VALUES (?, ?, 'house_ai', ?)
            """,
            (league_id, ai["id"], created),
        )
        self._audit(
            "league",
            league_id,
            "created",
            owner["id"],
            {"name": name.strip()},
        )
        return self.get_league(league_id, viewer=owner)

    def join_league(self, user: dict, invite_code: str) -> dict:
        row = self.db.fetchone(
            "SELECT * FROM leagues WHERE invite_code = ?", (invite_code.strip(),)
        )
        if not row:
            raise NotFoundError("Invite code not found")
        league = row_to_dict(row)
        assert league is not None
        existing = self.db.fetchone(
            """
            SELECT * FROM league_members
            WHERE league_id = ? AND user_id = ?
            """,
            (league["id"], user["id"]),
        )
        if existing and existing["removed_at_utc"] is None:
            return self.get_league(league["id"], viewer=user)
        joined = self._now()
        if existing:
            self.db.execute(
                """
                UPDATE league_members
                SET removed_at_utc = NULL, role = 'member', joined_at_utc = ?
                WHERE league_id = ? AND user_id = ?
                """,
                (joined, league["id"], user["id"]),
            )
        else:
            self.db.execute(
                """
                INSERT INTO league_members (league_id, user_id, role, joined_at_utc)
                VALUES (?, ?, 'member', ?)
                """,
                (league["id"], user["id"], joined),
            )
        self._audit("league", league["id"], "member_joined", user["id"], {"user_id": user["id"]})
        return self.get_league(league["id"], viewer=user)

    def require_member(self, league_id: str, user_id: str) -> dict:
        row = self.db.fetchone(
            """
            SELECT * FROM league_members
            WHERE league_id = ? AND user_id = ? AND removed_at_utc IS NULL
            """,
            (league_id, user_id),
        )
        if not row:
            raise ForbiddenError("Not a league member")
        return row_to_dict(row)  # type: ignore[return-value]

    def require_commissioner(self, league_id: str, user_id: str) -> dict:
        member = self.require_member(league_id, user_id)
        if member["role"] not in ("commissioner",):
            raise ForbiddenError("Commissioner role required")
        return member

    def get_league(self, league_id: str, viewer: dict | None = None) -> dict:
        row = self.db.fetchone("SELECT * FROM leagues WHERE id = ?", (league_id,))
        if not row:
            raise NotFoundError("League not found")
        league = row_to_dict(row)
        assert league is not None
        if viewer:
            self.require_member(league_id, viewer["id"])
        members = self.db.fetchall(
            """
            SELECT m.*, u.display_name, u.is_house_ai
            FROM league_members m
            JOIN users u ON u.id = m.user_id
            WHERE m.league_id = ? AND m.removed_at_utc IS NULL
            ORDER BY m.joined_at_utc
            """,
            (league_id,),
        )
        league["members"] = [row_to_dict(m) for m in members]
        return league

    def remove_member(self, commissioner: dict, league_id: str, target_user_id: str) -> dict:
        self.require_commissioner(league_id, commissioner["id"])
        league = self.get_league(league_id)
        if target_user_id == league["owner_user_id"]:
            raise ForbiddenError("Cannot remove league owner")
        target = self.db.fetchone(
            "SELECT * FROM users WHERE id = ?", (target_user_id,)
        )
        if target and target["is_house_ai"]:
            raise ForbiddenError("Cannot remove house AI contestant")
        self.db.execute(
            """
            UPDATE league_members SET removed_at_utc = ?
            WHERE league_id = ? AND user_id = ? AND removed_at_utc IS NULL
            """,
            (self._now(), league_id, target_user_id),
        )
        self._audit(
            "league",
            league_id,
            "member_removed",
            commissioner["id"],
            {"user_id": target_user_id},
            reason="commissioner_remove",
        )
        return self.get_league(league_id, viewer=commissioner)

    def list_leagues_for_user(self, user: dict) -> list[dict]:
        rows = self.db.fetchall(
            """
            SELECT l.*
            FROM leagues l
            JOIN league_members m ON m.league_id = l.id
            WHERE m.user_id = ? AND m.removed_at_utc IS NULL
            ORDER BY l.created_at_utc DESC
            """,
            (user["id"],),
        )
        return [row_to_dict(r) for r in rows]  # type: ignore[misc]

    # --- catalog helpers ----------------------------------------------

    def upsert_game(self, game: dict) -> dict:
        existing = self.db.fetchone("SELECT id FROM games WHERE id = ?", (game["id"],))
        if existing:
            self.db.execute(
                """
                UPDATE games SET season=?, home_team_id=?, away_team_id=?,
                  scheduled_tipoff_utc=?, status=?
                WHERE id=?
                """,
                (
                    game["season"],
                    game["home_team_id"],
                    game["away_team_id"],
                    game["scheduled_tipoff_utc"],
                    game.get("status", "scheduled"),
                    game["id"],
                ),
            )
        else:
            self.db.execute(
                """
                INSERT INTO games (id, season, home_team_id, away_team_id,
                  scheduled_tipoff_utc, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    game["id"],
                    game["season"],
                    game["home_team_id"],
                    game["away_team_id"],
                    game["scheduled_tipoff_utc"],
                    game.get("status", "scheduled"),
                ),
            )
        return row_to_dict(self.db.fetchone("SELECT * FROM games WHERE id = ?", (game["id"],)))  # type: ignore

    def upsert_player(self, player: dict) -> dict:
        existing = self.db.fetchone("SELECT id FROM players WHERE id = ?", (player["id"],))
        if existing:
            self.db.execute(
                """
                UPDATE players SET full_name=?, team_id=?, position=? WHERE id=?
                """,
                (
                    player["full_name"],
                    player["team_id"],
                    player.get("position"),
                    player["id"],
                ),
            )
        else:
            self.db.execute(
                """
                INSERT INTO players (id, full_name, team_id, position)
                VALUES (?, ?, ?, ?)
                """,
                (
                    player["id"],
                    player["full_name"],
                    player["team_id"],
                    player.get("position"),
                ),
            )
        return row_to_dict(self.db.fetchone("SELECT * FROM players WHERE id = ?", (player["id"],)))  # type: ignore

    # --- slates / questions -------------------------------------------

    def create_slate(
        self,
        actor: dict,
        league_id: str,
        *,
        date_utc: str,
        questions: list[dict],
        scoring_version: str = SCORING_VERSION,
    ) -> dict:
        """Create slate, freeze baselines, open questions."""
        self.require_commissioner(league_id, actor["id"])
        if not questions:
            raise ValidationError("At least one question is required")
        if scoring_version != SCORING_VERSION:
            raise ValidationError(f"Unsupported scoring_version: {scoring_version}")

        slate_id = new_id("slt_")
        created = self._now()
        self.db.execute(
            """
            INSERT INTO slates (id, league_id, date_utc, created_at_utc, status, scoring_version)
            VALUES (?, ?, ?, ?, 'open', ?)
            """,
            (slate_id, league_id, date_utc, created, scoring_version),
        )

        created_questions = []
        for q in questions:
            for key in ("game", "player", "stat", "frozen_baseline", "prompt_text"):
                if key not in q:
                    raise ValidationError(f"question missing {key}")
            self.upsert_game(q["game"])
            self.upsert_player(q["player"])
            tip = q.get("scheduled_tipoff_utc") or q["game"]["scheduled_tipoff_utc"]
            qid = new_id("q_")
            self.db.execute(
                """
                INSERT INTO questions (
                  id, slate_id, game_id, player_id, stat, scheduled_tipoff_utc,
                  frozen_baseline, baseline_version, status, prompt_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
                """,
                (
                    qid,
                    slate_id,
                    q["game"]["id"],
                    q["player"]["id"],
                    q["stat"].upper(),
                    tip,
                    float(q["frozen_baseline"]),
                    q.get("baseline_version", BASELINE_VERSION),
                    q["prompt_text"],
                ),
            )
            created_questions.append(qid)

        # House AI enters immediately under identical rules, using the frozen baseline
        # as its numerical prediction (transparent, auditable, before tipoff).
        ai = self.ensure_house_ai()
        now_dt = self._clock()
        for qid, q in zip(created_questions, questions):
            tip = q.get("scheduled_tipoff_utc") or q["game"]["scheduled_tipoff_utc"]
            if parse_iso(tip) <= now_dt:
                continue  # identical lock rules — no late AI entry
            self.submit_forecast(
                ai,
                qid,
                float(q["frozen_baseline"]),
                client_request_id=f"house-ai-baseline-{qid}",
            )

        self._audit(
            "slate",
            slate_id,
            "created_with_frozen_baselines",
            actor["id"],
            {
                "question_ids": created_questions,
                "scoring_version": scoring_version,
                "baseline_version": BASELINE_VERSION,
                "house_ai_seeded": True,
            },
        )
        return self.get_slate(slate_id, viewer=actor)

    def get_slate(self, slate_id: str, viewer: dict | None = None) -> dict:
        row = self.db.fetchone("SELECT * FROM slates WHERE id = ?", (slate_id,))
        if not row:
            raise NotFoundError("Slate not found")
        slate = row_to_dict(row)
        assert slate is not None
        if viewer:
            self.require_member(slate["league_id"], viewer["id"])
        qs = self.db.fetchall(
            """
            SELECT q.*, p.full_name AS player_name, g.home_team_id, g.away_team_id
            FROM questions q
            JOIN players p ON p.id = q.player_id
            JOIN games g ON g.id = q.game_id
            WHERE q.slate_id = ?
            ORDER BY q.scheduled_tipoff_utc, q.id
            """,
            (slate_id,),
        )
        questions = []
        now = self._clock()
        for q in qs:
            item = row_to_dict(q)
            assert item is not None
            locked = parse_iso(item["scheduled_tipoff_utc"]) <= now or item["status"] in (
                "locked",
                "settled",
                "void",
            )
            item["is_locked"] = locked
            if viewer:
                mine = self._latest_forecast(item["id"], viewer["id"])
                item["my_prediction"] = mine
            if locked:
                item["forecasts"] = self._forecasts_for_question(item["id"])
            else:
                item["forecasts"] = None  # hidden until lock
            result = self.db.fetchone(
                "SELECT * FROM results WHERE question_id = ?", (item["id"],)
            )
            item["result"] = row_to_dict(result)
            questions.append(item)
        slate["questions"] = questions
        return slate

    def current_slate(self, league_id: str, viewer: dict) -> dict | None:
        self.require_member(league_id, viewer["id"])
        row = self.db.fetchone(
            """
            SELECT * FROM slates
            WHERE league_id = ?
            ORDER BY date_utc DESC, created_at_utc DESC
            LIMIT 1
            """,
            (league_id,),
        )
        if not row:
            return None
        return self.get_slate(row["id"], viewer=viewer)

    # --- forecasts ----------------------------------------------------

    def _latest_forecast(self, question_id: str, user_id: str) -> dict | None:
        row = self.db.fetchone(
            """
            SELECT * FROM forecast_events
            WHERE question_id = ? AND user_id = ?
              AND event_type IN ('submit', 'correction')
            ORDER BY received_at_utc DESC, rowid DESC
            LIMIT 1
            """,
            (question_id, user_id),
        )
        return row_to_dict(row)

    def _forecasts_for_question(self, question_id: str) -> list[dict]:
        rows = self.db.fetchall(
            """
            SELECT f.*, u.display_name, u.is_house_ai
            FROM forecast_events f
            JOIN users u ON u.id = f.user_id
            WHERE f.id IN (
              SELECT f2.id FROM forecast_events f2
              WHERE f2.question_id = ?
                AND f2.event_type IN ('submit', 'correction')
                AND f2.received_at_utc = (
                  SELECT MAX(f3.received_at_utc) FROM forecast_events f3
                  WHERE f3.question_id = f2.question_id
                    AND f3.user_id = f2.user_id
                    AND f3.event_type IN ('submit', 'correction')
                )
            )
            ORDER BY u.display_name
            """,
            (question_id,),
        )
        # Deduplicate by user (same timestamp edge case)
        seen: set[str] = set()
        out: list[dict] = []
        for r in rows:
            if r["user_id"] in seen:
                continue
            seen.add(r["user_id"])
            out.append(row_to_dict(r))  # type: ignore[arg-type]
        return out

    def _get_question(self, question_id: str) -> dict:
        row = self.db.fetchone("SELECT * FROM questions WHERE id = ?", (question_id,))
        if not row:
            raise NotFoundError("Question not found")
        return row_to_dict(row)  # type: ignore[return-value]

    def _question_league_id(self, question_id: str) -> str:
        row = self.db.fetchone(
            """
            SELECT s.league_id FROM questions q
            JOIN slates s ON s.id = q.slate_id
            WHERE q.id = ?
            """,
            (question_id,),
        )
        if not row:
            raise NotFoundError("Question not found")
        return row["league_id"]

    def submit_forecast(
        self,
        user: dict,
        question_id: str,
        predicted_value: float,
        *,
        client_request_id: str | None = None,
        now: str | None = None,
    ) -> dict:
        question = self._get_question(question_id)
        league_id = self._question_league_id(question_id)
        self.require_member(league_id, user["id"])

        if question["status"] == "void":
            raise ConflictError("Question is void")

        received = now or self._now()
        if parse_iso(received) >= parse_iso(question["scheduled_tipoff_utc"]):
            raise LockPassedError(
                f"Submission locked at tipoff {question['scheduled_tipoff_utc']}"
            )
        if question["status"] not in ("open",):
            raise LockPassedError("Question is not open for submissions")

        if client_request_id:
            existing = self.db.fetchone(
                """
                SELECT * FROM forecast_events
                WHERE question_id = ? AND user_id = ? AND client_request_id = ?
                """,
                (question_id, user["id"], client_request_id),
            )
            if existing:
                return row_to_dict(existing)  # type: ignore[return-value]

        prior = self._latest_forecast(question_id, user["id"])
        event_id = new_id("fc_")
        self.db.execute(
            """
            INSERT INTO forecast_events (
              id, question_id, user_id, predicted_value, received_at_utc,
              event_type, reason, actor_user_id, prior_event_id, client_request_id
            ) VALUES (?, ?, ?, ?, ?, 'submit', NULL, ?, ?, ?)
            """,
            (
                event_id,
                question_id,
                user["id"],
                float(predicted_value),
                received,
                user["id"],
                prior["id"] if prior else None,
                client_request_id,
            ),
        )
        self._audit(
            "forecast",
            event_id,
            "submit",
            user["id"],
            {
                "question_id": question_id,
                "predicted_value": float(predicted_value),
                "prior_event_id": prior["id"] if prior else None,
            },
        )
        return row_to_dict(
            self.db.fetchone("SELECT * FROM forecast_events WHERE id = ?", (event_id,))
        )  # type: ignore[return-value]

    def correct_forecast(
        self,
        commissioner: dict,
        question_id: str,
        target_user_id: str,
        predicted_value: float,
        reason: str,
    ) -> dict:
        if not reason or not reason.strip():
            raise ValidationError("Correction reason is required")
        league_id = self._question_league_id(question_id)
        self.require_commissioner(league_id, commissioner["id"])
        prior = self._latest_forecast(question_id, target_user_id)
        event_id = new_id("fc_")
        received = self._now()
        self.db.execute(
            """
            INSERT INTO forecast_events (
              id, question_id, user_id, predicted_value, received_at_utc,
              event_type, reason, actor_user_id, prior_event_id, client_request_id
            ) VALUES (?, ?, ?, ?, ?, 'correction', ?, ?, ?, NULL)
            """,
            (
                event_id,
                question_id,
                target_user_id,
                float(predicted_value),
                received,
                reason.strip(),
                commissioner["id"],
                prior["id"] if prior else None,
            ),
        )
        self._audit(
            "forecast",
            event_id,
            "correction",
            commissioner["id"],
            {
                "question_id": question_id,
                "user_id": target_user_id,
                "predicted_value": float(predicted_value),
                "prior_event_id": prior["id"] if prior else None,
            },
            reason=reason.strip(),
        )
        # Recalculate grade if result exists
        result = self.db.fetchone(
            "SELECT * FROM results WHERE question_id = ?", (question_id,)
        )
        if result:
            self._grade_one(question_id, target_user_id)
        return row_to_dict(
            self.db.fetchone("SELECT * FROM forecast_events WHERE id = ?", (event_id,))
        )  # type: ignore[return-value]

    def void_question(self, commissioner: dict, question_id: str, reason: str) -> dict:
        if not reason or not reason.strip():
            raise ValidationError("Void reason is required")
        question = self._get_question(question_id)
        league_id = self._question_league_id(question_id)
        self.require_commissioner(league_id, commissioner["id"])
        self.db.execute(
            "UPDATE questions SET status = 'void' WHERE id = ?",
            (question_id,),
        )
        self.db.execute("DELETE FROM grades WHERE question_id = ?", (question_id,))
        self._audit(
            "question",
            question_id,
            "void",
            commissioner["id"],
            {"prior_status": question["status"]},
            reason=reason.strip(),
        )
        return self._get_question(question_id)

    # --- results & grading --------------------------------------------

    def ingest_result(
        self,
        actor: dict,
        question_id: str,
        *,
        actual_value: float,
        source_url: str,
        fetched_at_utc: str,
        source_updated_at_utc: str | None = None,
        fixture_id: str | None = None,
        status: str = "official",
    ) -> dict:
        if not source_url:
            raise ValidationError("source_url is required — never invent results")
        question = self._get_question(question_id)
        if question["status"] == "void":
            raise ConflictError("Cannot settle a void question")
        league_id = self._question_league_id(question_id)
        self.require_commissioner(league_id, actor["id"])

        existing = self.db.fetchone(
            "SELECT * FROM results WHERE question_id = ?", (question_id,)
        )
        if existing:
            self.db.execute(
                """
                UPDATE results SET actual_value=?, source_url=?, fetched_at_utc=?,
                  source_updated_at_utc=?, status=?, fixture_id=?
                WHERE question_id=?
                """,
                (
                    float(actual_value),
                    source_url,
                    fetched_at_utc,
                    source_updated_at_utc,
                    status,
                    fixture_id,
                    question_id,
                ),
            )
            action = "result_corrected"
        else:
            self.db.execute(
                """
                INSERT INTO results (
                  question_id, actual_value, source_url, fetched_at_utc,
                  source_updated_at_utc, status, fixture_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    question_id,
                    float(actual_value),
                    source_url,
                    fetched_at_utc,
                    source_updated_at_utc,
                    status,
                    fixture_id,
                ),
            )
            action = "result_ingested"

        self.db.execute(
            "UPDATE questions SET status = 'settled' WHERE id = ?",
            (question_id,),
        )
        self._audit(
            "result",
            question_id,
            action,
            actor["id"],
            {
                "actual_value": float(actual_value),
                "source_url": source_url,
                "fetched_at_utc": fetched_at_utc,
                "fixture_id": fixture_id,
            },
        )
        return row_to_dict(
            self.db.fetchone("SELECT * FROM results WHERE question_id = ?", (question_id,))
        )  # type: ignore[return-value]

    def _grade_one(self, question_id: str, user_id: str) -> dict | None:
        question = self._get_question(question_id)
        if question["status"] == "void":
            return None
        result = self.db.fetchone(
            "SELECT * FROM results WHERE question_id = ?", (question_id,)
        )
        if not result:
            return None
        forecast = self._latest_forecast(question_id, user_id)
        if not forecast:
            return None
        slate = self.db.fetchone(
            "SELECT scoring_version FROM slates WHERE id = ?", (question["slate_id"],)
        )
        assert slate is not None
        graded = grade_prediction(
            forecast["predicted_value"],
            result["actual_value"],
            question["frozen_baseline"],
            question["stat"],
            scoring_version=slate["scoring_version"],
        )
        computed = self._now()
        self.db.execute(
            """
            INSERT INTO grades (
              question_id, user_id, score, baseline_score, skill_delta,
              scoring_version, computed_at_utc, source_result_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(question_id, user_id) DO UPDATE SET
              score=excluded.score,
              baseline_score=excluded.baseline_score,
              skill_delta=excluded.skill_delta,
              scoring_version=excluded.scoring_version,
              computed_at_utc=excluded.computed_at_utc,
              source_result_id=excluded.source_result_id
            """,
            (
                question_id,
                user_id,
                graded.score,
                graded.baseline_score,
                graded.skill_delta,
                graded.scoring_version,
                computed,
                question_id,
            ),
        )
        return row_to_dict(
            self.db.fetchone(
                "SELECT * FROM grades WHERE question_id = ? AND user_id = ?",
                (question_id, user_id),
            )
        )

    def grade_slate(self, actor: dict, slate_id: str) -> dict:
        slate = self.get_slate(slate_id)
        self.require_commissioner(slate["league_id"], actor["id"])
        graded = []
        for q in slate["questions"]:
            if q["status"] == "void":
                continue
            result = self.db.fetchone(
                "SELECT * FROM results WHERE question_id = ?", (q["id"],)
            )
            if not result:
                continue
            # Grade every member who submitted
            forecasts = self._forecasts_for_question(q["id"])
            for f in forecasts:
                g = self._grade_one(q["id"], f["user_id"])
                if g:
                    graded.append(g)
        self.db.execute(
            "UPDATE slates SET status = 'graded', locked_at_utc = COALESCE(locked_at_utc, ?) WHERE id = ?",
            (self._now(), slate_id),
        )
        self._audit(
            "slate",
            slate_id,
            "graded",
            actor["id"],
            {"grade_count": len(graded)},
        )
        return {
            "slate_id": slate_id,
            "grades": graded,
            "leaderboard": self.leaderboard(slate["league_id"], actor, window="slate", slate_id=slate_id),
        }

    def leaderboard(
        self,
        league_id: str,
        viewer: dict,
        *,
        window: str = "slate",
        slate_id: str | None = None,
    ) -> dict:
        self.require_member(league_id, viewer["id"])
        if window == "slate":
            if not slate_id:
                current = self.db.fetchone(
                    """
                    SELECT id FROM slates WHERE league_id = ?
                    ORDER BY date_utc DESC LIMIT 1
                    """,
                    (league_id,),
                )
                if not current:
                    return {
                        "league_id": league_id,
                        "window": window,
                        "scoring_basis": "mean_accuracy",
                        "entries": [],
                    }
                slate_id = current["id"]
            rows = self.db.fetchall(
                """
                SELECT g.user_id, u.display_name, u.is_house_ai,
                       AVG(g.score) AS mean_score,
                       COUNT(*) AS completed_count,
                       AVG(g.skill_delta) AS mean_skill_delta
                FROM grades g
                JOIN questions q ON q.id = g.question_id
                JOIN users u ON u.id = g.user_id
                WHERE q.slate_id = ? AND q.status != 'void'
                GROUP BY g.user_id
                ORDER BY mean_score DESC, completed_count DESC, u.display_name
                """,
                (slate_id,),
            )
        else:
            rows = self.db.fetchall(
                """
                SELECT g.user_id, u.display_name, u.is_house_ai,
                       AVG(g.score) AS mean_score,
                       COUNT(*) AS completed_count,
                       AVG(g.skill_delta) AS mean_skill_delta
                FROM grades g
                JOIN questions q ON q.id = g.question_id
                JOIN slates s ON s.id = q.slate_id
                JOIN users u ON u.id = g.user_id
                WHERE s.league_id = ? AND q.status != 'void'
                GROUP BY g.user_id
                ORDER BY mean_score DESC, completed_count DESC, u.display_name
                """,
                (league_id,),
            )

        entries = []
        for rank, r in enumerate(rows, start=1):
            n = int(r["completed_count"])
            entries.append(
                {
                    "rank": rank,
                    "user_id": r["user_id"],
                    "display_name": r["display_name"],
                    "is_house_ai": bool(r["is_house_ai"]),
                    "mean_accuracy": round(float(r["mean_score"]), 2),
                    "completed_count": n,
                    "provisional": is_provisional(n),
                    "experimental_mean_skill_delta": round(float(r["mean_skill_delta"]), 2),
                }
            )
        return {
            "league_id": league_id,
            "window": window,
            "slate_id": slate_id,
            "scoring_basis": "mean_accuracy",
            "skill_score_note": "experimental_mean_skill_delta is informational only",
            "entries": entries,
        }

    def audit_for_question(self, viewer: dict, question_id: str) -> dict:
        league_id = self._question_league_id(question_id)
        self.require_member(league_id, viewer["id"])
        rows = self.db.fetchall(
            """
            SELECT * FROM audit_log
            WHERE (entity_type = 'question' AND entity_id = ?)
               OR (entity_type = 'result' AND entity_id = ?)
               OR (entity_type = 'forecast' AND payload_json LIKE ?)
            ORDER BY created_at_utc, id
            """,
            (question_id, question_id, f'%"{question_id}"%'),
        )
        out = []
        for r in rows:
            item = row_to_dict(r)
            assert item is not None
            import json

            item["payload"] = json.loads(item.pop("payload_json"))
            out.append(item)
        # Also include forecast events as audit surface
        events = self.db.fetchall(
            """
            SELECT * FROM forecast_events WHERE question_id = ?
            ORDER BY received_at_utc, id
            """,
            (question_id,),
        )
        return {
            "question_id": question_id,
            "audit_log": out,
            "forecast_events": [row_to_dict(e) for e in events],
        }  # type: ignore[return-value]

    def lock_due_questions(self) -> int:
        """Mark open questions past tipoff as locked (server-side)."""
        now = self._now()
        cur = self.db.execute(
            """
            UPDATE questions SET status = 'locked'
            WHERE status = 'open' AND scheduled_tipoff_utc <= ?
            """,
            (now,),
        )
        return cur.rowcount

    # --- audit helper -------------------------------------------------

    def _audit(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        actor_user_id: str,
        payload: dict[str, Any],
        reason: str | None = None,
    ) -> None:
        self.db.execute(
            """
            INSERT INTO audit_log (
              id, entity_type, entity_id, action, actor_user_id, reason,
              payload_json, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("aud_"),
                entity_type,
                entity_id,
                action,
                actor_user_id,
                reason,
                dumps(payload),
                self._now(),
            ),
        )
