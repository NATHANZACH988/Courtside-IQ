# Agency → Courtside IQ bridge

**Purpose.** The Sports Analytics Agency (owner's internal research desk) is the
measurement engine behind Courtside IQ. This document maps agency artifacts to
Courtside entities so the product never re-derives what the lab already
measures, and the lab's findings reach the product with provenance intact.

**Status:** contribution from Pax (agency operator), per owner direction
2026-10-23. No API contract changes. Nothing here is deployed product code.

## Artifact mapping

| Agency artifact | Courtside consumer | Rule |
|---|---|---|
| `data/gameflow/<league>/<date>/<event>.json` (per-game flow file: segment scores, runs, foul caps, usage surges, full player lines) | `result` provenance + postgame grading inputs | Final box scores only for settlement; source = ESPN summary feed, fetched_at recorded per run |
| `data/scoring_profiles.json` (per-player: games, starts, min/g, pts/g, FGA/min, PF/36, capped/cannibal/victim event counts) | `question.frozen_baseline` inputs; FULL_ROSTER_PROP_SCREENING `candidate_ledger` | Snapshot is timestamped and frozen at slate creation; `baseline_version` = profiles generation date + agency git hash |
| Live watcher flags (in-game foul caps, persistent bench surges) | In-game research view only | Never alters locked forecasts or baselines (per GAME_FLOW_INTELLIGENCE.md) |
| Pattern notes (`pattern_notes.jsonl`, deduped by event+type+player) | Research findings feed | Observed facts about completed games; predictive value unproven until prospective grading passes the repo's gates |

## Operating rules inherited from the agency

1. **Evidence labels.** Every number is an observed box-score fact, a computed
   rate, or a hypothesis. The three are never blended in one claim.
2. **No sportsbook fields.** Consistent with the beta API contract — the
   agency's independent projections are produced before any market comparison,
   and market data is never an input.
3. **Five-game gate.** No Play-grade output for a team until five current-season
   games are banked, absent explicit owner override (matches
   FULL_ROSTER_PROP_SCREENING.md).
4. **Retractions are published, not edited away.** Detector errors are logged
   with the affected events named (see findings doc) so downstream consumers
   can discount contaminated entries.
5. **Code provenance.** `research/gameflow/*.py` are byte-identical copies of
   the production scripts running nightly in the agency. One deployment
   constant (`BASE` path) must be adapted on import.

## What the agency is still building (not in this PR)

- Prospective prediction log: named pre-tip predictions (player, mechanism,
  direction) graded post-game — the promotion path for every finding here.
- Coach-specific next-substitution baselines (Courtside spec §2) — the watcher
  detects surges today; forecasting the next sub is the next layer.
- Conservation checks (team minutes/opportunities reconciliation) across
  profile outputs.
