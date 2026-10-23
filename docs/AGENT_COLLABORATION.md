# Courtside IQ — collaboration protocol

Goal: verified mobile-first NBA research beta with a free prediction challenge. No wagering or prizes. Five current-season banked games per team are required before a Play verdict, absent owner override.

- ChatGPT owns research/, data provenance, grading and integration; branch feat/research-pipeline.
- Grok owns web/, Prediction Arena, leagues and leaderboard; branch feat/prediction-arena.
- Cursor works in independent integration/test branches.
- docs/API_CONTRACT.md is shared; changes require review by both agents.
- No agent self-merges; repository owner authorizes merges and releases.

Every PR must include summary, test commands/results, evidence sources, license assumptions, security implications and rollback plan.

Release gates: immutable submission history; server-side tipoff locks; reproducible normalized grading; provisional sample-size-aware leaderboard; source-attributed settlements; no secrets or fabricated live data; mobile tests and independent review.

No agent can automatically invoke another from this chat. Coordinate via GitHub PRs and explicit handoffs.
