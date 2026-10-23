"""SQLite persistence for the Prediction Arena beta."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    email TEXT UNIQUE,
    is_house_ai INTEGER NOT NULL DEFAULT 0,
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    created_at_utc TEXT NOT NULL,
    expires_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leagues (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_user_id TEXT NOT NULL REFERENCES users(id),
    visibility TEXT NOT NULL DEFAULT 'invite',
    invite_code TEXT UNIQUE NOT NULL,
    created_at_utc TEXT NOT NULL,
    no_prize_notice TEXT NOT NULL DEFAULT 'Free, invite-only, no prizes.'
);

CREATE TABLE IF NOT EXISTS league_members (
    league_id TEXT NOT NULL REFERENCES leagues(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    role TEXT NOT NULL,
    joined_at_utc TEXT NOT NULL,
    removed_at_utc TEXT,
    PRIMARY KEY (league_id, user_id)
);

CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
    season TEXT NOT NULL,
    home_team_id TEXT NOT NULL,
    away_team_id TEXT NOT NULL,
    scheduled_tipoff_utc TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    team_id TEXT NOT NULL,
    position TEXT
);

CREATE TABLE IF NOT EXISTS slates (
    id TEXT PRIMARY KEY,
    league_id TEXT NOT NULL REFERENCES leagues(id),
    date_utc TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    locked_at_utc TEXT,
    status TEXT NOT NULL,
    scoring_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    slate_id TEXT NOT NULL REFERENCES slates(id),
    game_id TEXT NOT NULL REFERENCES games(id),
    player_id TEXT NOT NULL REFERENCES players(id),
    stat TEXT NOT NULL,
    scheduled_tipoff_utc TEXT NOT NULL,
    frozen_baseline REAL NOT NULL,
    baseline_version TEXT NOT NULL,
    status TEXT NOT NULL,
    prompt_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forecast_events (
    id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL REFERENCES questions(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    predicted_value REAL NOT NULL,
    received_at_utc TEXT NOT NULL,
    event_type TEXT NOT NULL,
    reason TEXT,
    actor_user_id TEXT NOT NULL REFERENCES users(id),
    prior_event_id TEXT,
    client_request_id TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_forecast_idempotency
ON forecast_events(question_id, user_id, client_request_id)
WHERE client_request_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS results (
    question_id TEXT PRIMARY KEY REFERENCES questions(id),
    actual_value REAL NOT NULL,
    source_url TEXT NOT NULL,
    fetched_at_utc TEXT NOT NULL,
    source_updated_at_utc TEXT,
    status TEXT NOT NULL,
    fixture_id TEXT
);

CREATE TABLE IF NOT EXISTS grades (
    question_id TEXT NOT NULL REFERENCES questions(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    score REAL NOT NULL,
    baseline_score REAL NOT NULL,
    skill_delta REAL NOT NULL,
    scoring_version TEXT NOT NULL,
    computed_at_utc TEXT NOT NULL,
    source_result_id TEXT NOT NULL,
    PRIMARY KEY (question_id, user_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor_user_id TEXT NOT NULL,
    reason TEXT,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self.migrate()

    def migrate(self) -> None:
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        cur = self._conn.execute(sql, params)
        self._conn.commit()
        return cur

    def executemany(self, sql: str, seq: list) -> None:
        self._conn.executemany(sql, seq)
        self._conn.commit()

    def fetchone(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        return self._conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        return list(self._conn.execute(sql, params).fetchall())

    def close(self) -> None:
        self._conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def dumps(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
