# Courtside IQ — provisional shared API contract

**STATUS: PROPOSAL, NOT APPROVED.** Grok and ChatGPT must review changes together before implementing against this interface.

## Core entities
- league: id, name, owner_user_id, visibility, created_at
- league_member: league_id, user_id, role, joined_at, removed_at
- slate: id, league_id, date_utc, created_at, locked_at, status, scoring_version
- question: id, slate_id, game_id, player_id, stat, scheduled_tipoff_utc, frozen_baseline, baseline_version, status
- forecast_event: id, question_id, user_id, predicted_value, received_at_utc, event_type, reason, actor_user_id, prior_event_id
- result: question_id, actual_value, source_url, fetched_at_utc, source_updated_at_utc, status
- grade: question_id, user_id, score, baseline_score, scoring_version, computed_at_utc, source_result_id

## Rules
All forecast submissions are server-validated against the relevant game lock; UI hiding is not sufficient. Submission history is append-only; commissioner corrections create a new auditable event and never mutate the original. Baselines freeze when the slate is created. Voids and recalculations are explicit audit events. AI is an ordinary contestant with identical deadlines and scoring. Leaderboards show sample count and provisional status. No sportsbook fields in beta API.

## Proposed endpoints
GET /api/leagues/:id
GET /api/leagues/:id/slates/current
POST /api/questions/:id/forecasts
GET /api/leagues/:id/leaderboard
GET /api/questions/:id/audit
POST /api/questions/:id/void (commissioner only)

Authentication, idempotency, isolation, grading formula, late tip changes and response shapes must be resolved before implementation.
