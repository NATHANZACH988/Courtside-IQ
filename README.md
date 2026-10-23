# Courtside IQ — NBA Intelligence + Prediction Arena

**Status:** development prototype, not deployed.

Courtside IQ combines transparent NBA research with a free, no-prize forecasting competition. Beta features include fixed nightly slates, numerical player-stat forecasts, server-side locks, auditable grading, and league-first mobile UX.

## Ownership
- ChatGPT: research pipeline, provenance, grading, integration and CI
- Grok: Prediction Arena, leagues, leaderboards, mobile UX
- Cursor: integration and tests on separate branches

See docs/AGENT_COLLABORATION.md and docs/API_CONTRACT.md. Do not display synthetic statistics as live. No wagers, prizes, or verified betting-edge claims.

## Current codebase (Cursor vertical slice)

The original 34-file starter ZIP was **not available** in this environment (see docs/IMPORT_STATUS.md). Cursor scaffolded a working prediction-to-grading slice:

| Path | Purpose |
|------|---------|
| `arena/` | Leagues, slates, forecasts, locks, grading, leaderboard, audit |
| `research/` | Doctrine gates, foul trouble, hot/cold streaks |
| `web/` | Mobile-first league UI |
| `fixtures/box_scores/` | Source-attributed offline results |
| `docs/SCHEMA_PROPOSAL.md` | Schema/API proposal for joint review |
| `docs/SCORING_V1.md` | Public closeness-v1 scoring explanation |

### Quick start

```bash
PYTHONPATH=. python -m arena.api
```

### Tests

```bash
PYTHONPATH=. python -m unittest discover -s research/tests -p 'test_*.py' -v
PYTHONPATH=. python -m unittest discover -s arena/tests -p 'test_*.py' -v
PYTHONPATH=. python -m unittest discover -s tests -p 'test_*.py' -v
```

### Live data (beta research)

```bash
PYTHONPATH=. python3 scripts/capture_live_game.py --event-id 401909848
PYTHONPATH=. python3 scripts/grade_live_fixture.py
```

Tonight’s completed CHI@MIL final was captured with source URL + fetch timestamp under
`fixtures/box_scores/live_captures/`. NBA.com CDN may 403; ESPN public JSON is used for
research captures. **Commercial rights are unverified — do not deploy publicly without review.**

This README does **not** mean the product is deployed.
