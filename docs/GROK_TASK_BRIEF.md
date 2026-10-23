# Grok — Courtside IQ work assignment

Work on feat/prediction-arena. Implement a league-first mobile beta with a fixed nightly slate, numeric player-stat forecasts, pre-tip server lock, transparent closeness scoring, provisional leaderboards and audited commissioner controls.

Keep the experience free, invite-only and no-prize. Do not add sportsbook odds, streaks, prizes, payouts or betting copy. Do not represent demo records as real NBA data.

Read docs/AGENT_COLLABORATION.md and docs/API_CONTRACT.md. The API contract is provisional; propose changes in a separate document or PR comment and seek joint review before editing it.

Provide sourced competitor analysis distinguishing observed facts, inferences and unverified claims. Include tests for lock deadlines, duplicate submissions, league isolation, commissioner permissions, immutable events, scoring reproducibility, and actual box-score provenance. Live data tests should report skipped with reason if unavailable; offline fixture tests must still run.

Open a PR with screenshots, exact test results and limitations. Do not merge your own PR.
