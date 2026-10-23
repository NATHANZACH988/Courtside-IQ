# Schema & API proposal (for joint review)

**STATUS: PROPOSAL — do not treat as the approved contract.**
`docs/API_CONTRACT.md` remains the shared provisional contract. This document
extends it with concrete SQL shapes, auth, and response envelopes for Cursor's
vertical-slice implementation. ChatGPT + Grok should review before promoting
any field into the shared contract.

## Design choices (beta)

| Choice | Decision | Notes |
|--------|----------|-------|
| Database | SQLite file for local/beta | Swap to Postgres later; same SQL dialect subset |
| Auth | Invite-token + session cookie / bearer | No OAuth in beta |
| IDs | UUID v4 strings | Stable across exports |
| Time | Always UTC ISO-8601 with `Z` | Tipoff locks use server clock |
| Money/odds | Absent | Hard rule for beta |

## Tables

### users
- `id` TEXT PK
- `display_name` TEXT NOT NULL
- `email` TEXT UNIQUE NULL
- `is_house_ai` INTEGER NOT NULL DEFAULT 0
- `created_at_utc` TEXT NOT NULL

### sessions
- `token` TEXT PK
- `user_id` TEXT NOT NULL REFERENCES users(id)
- `created_at_utc` TEXT NOT NULL
- `expires_at_utc` TEXT NOT NULL

### leagues
- `id` TEXT PK
- `name` TEXT NOT NULL
- `owner_user_id` TEXT NOT NULL REFERENCES users(id)
- `visibility` TEXT NOT NULL DEFAULT 'invite'  -- invite | private
- `invite_code` TEXT UNIQUE NOT NULL
- `created_at_utc` TEXT NOT NULL
- `no_prize_notice` TEXT NOT NULL DEFAULT 'Free, invite-only, no prizes.'

### league_members
- `league_id` TEXT NOT NULL
- `user_id` TEXT NOT NULL
- `role` TEXT NOT NULL  -- commissioner | member | house_ai
- `joined_at_utc` TEXT NOT NULL
- `removed_at_utc` TEXT NULL
- PRIMARY KEY (league_id, user_id)

### games
- `id` TEXT PK
- `season` TEXT NOT NULL
- `home_team_id` TEXT NOT NULL
- `away_team_id` TEXT NOT NULL
- `scheduled_tipoff_utc` TEXT NOT NULL
- `status` TEXT NOT NULL  -- scheduled | in_progress | final | postponed

### players
- `id` TEXT PK
- `full_name` TEXT NOT NULL
- `team_id` TEXT NOT NULL
- `position` TEXT NULL

### slates
- `id` TEXT PK
- `league_id` TEXT NOT NULL REFERENCES leagues(id)
- `date_utc` TEXT NOT NULL
- `created_at_utc` TEXT NOT NULL
- `locked_at_utc` TEXT NULL
- `status` TEXT NOT NULL  -- open | locked | graded | void
- `scoring_version` TEXT NOT NULL

### questions
- `id` TEXT PK
- `slate_id` TEXT NOT NULL REFERENCES slates(id)
- `game_id` TEXT NOT NULL REFERENCES games(id)
- `player_id` TEXT NOT NULL REFERENCES players(id)
- `stat` TEXT NOT NULL  -- PTS|REB|AST|FG3M|STL|BLK|TOV
- `scheduled_tipoff_utc` TEXT NOT NULL
- `frozen_baseline` REAL NOT NULL
- `baseline_version` TEXT NOT NULL
- `status` TEXT NOT NULL  -- open | locked | settled | void
- `prompt_text` TEXT NOT NULL

### forecast_events (append-only)
- `id` TEXT PK
- `question_id` TEXT NOT NULL
- `user_id` TEXT NOT NULL
- `predicted_value` REAL NOT NULL
- `received_at_utc` TEXT NOT NULL
- `event_type` TEXT NOT NULL  -- submit | correction | void_effect
- `reason` TEXT NULL
- `actor_user_id` TEXT NOT NULL
- `prior_event_id` TEXT NULL
- `client_request_id` TEXT NULL  -- idempotency

Unique index: active submission uniqueness enforced in application by selecting
the latest non-superseded event per (question_id, user_id).

### results
- `question_id` TEXT PK
- `actual_value` REAL NOT NULL
- `source_url` TEXT NOT NULL
- `fetched_at_utc` TEXT NOT NULL
- `source_updated_at_utc` TEXT NULL
- `status` TEXT NOT NULL  -- official | corrected | disputed
- `fixture_id` TEXT NULL  -- offline fixture attribution

### grades
- `question_id` TEXT NOT NULL
- `user_id` TEXT NOT NULL
- `score` REAL NOT NULL
- `baseline_score` REAL NOT NULL
- `skill_delta` REAL NOT NULL
- `scoring_version` TEXT NOT NULL
- `computed_at_utc` TEXT NOT NULL
- `source_result_id` TEXT NOT NULL
- PRIMARY KEY (question_id, user_id)

### audit_log
- `id` TEXT PK
- `entity_type` TEXT NOT NULL
- `entity_id` TEXT NOT NULL
- `action` TEXT NOT NULL
- `actor_user_id` TEXT NOT NULL
- `reason` TEXT NULL
- `payload_json` TEXT NOT NULL
- `created_at_utc` TEXT NOT NULL

## Proposed endpoint envelopes

All JSON responses:

```json
{ "ok": true, "data": { ... } }
{ "ok": false, "error": { "code": "LOCK_PASSED", "message": "..." } }
```

### Auth
- `POST /api/auth/demo-login` — beta-only demo sessions (`{display_name}`)
- `POST /api/auth/logout`

### Leagues
- `POST /api/leagues` — create league (caller becomes commissioner)
- `POST /api/leagues/join` — `{invite_code}`
- `GET /api/leagues/:id`
- `GET /api/leagues/:id/members`
- `POST /api/leagues/:id/members/:user_id/remove` — commissioner

### Slates & forecasts
- `POST /api/leagues/:id/slates` — create slate + questions + freeze baselines
- `GET /api/leagues/:id/slates/current`
- `POST /api/questions/:id/forecasts` — `{predicted_value, client_request_id?}`
- `GET /api/questions/:id/forecasts` — hidden until lock; own always visible
- `POST /api/questions/:id/void` — commissioner + reason
- `POST /api/questions/:id/corrections` — commissioner correction event

### Settlement & leaderboard
- `POST /api/questions/:id/results` — ingest attributed box score
- `POST /api/slates/:id/grade`
- `GET /api/leagues/:id/leaderboard?window=slate|season`
- `GET /api/questions/:id/audit`

## Open items needing owner/agent review

1. Exact provisional threshold (`n < 5` proposed).
2. Whether tipoff lock is per-question or whole-slate.
   **Implementation assumption:** per-question tipoff (matches contract).
3. Demo-login vs invite-email auth for private beta.
4. Commercial rights for any live NBA feed before deployment.
5. Promoting this schema into `docs/API_CONTRACT.md`.

## Out of scope (unchanged)

Real-money betting, prizes, sportsbook fields, chat, streak mechanics, cryptographic commitments.
