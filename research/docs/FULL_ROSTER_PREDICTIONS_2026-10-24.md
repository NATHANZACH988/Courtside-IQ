# Full-roster universe + prospective prediction log (agency contribution, 2026-10-24)

## Summary

PR #5's review named two remaining blockers in the agency bridge:
*"Full current-season roster universe and prospective predictions are
not implemented."* Both were built in the agency on 2026-10-24 under a
new owner directive — the model must reach **every** player, bench and
starters alike, and must **predict** the game-flow patterns (bench
eruption, starter suppression) before tip instead of only detecting
them live. This PR contributes that work, stacked on
`pax/agency-research-bridge` the same way PR #5 is stacked.

## What is included

- `research/gameflow/full_roster_board.py` — aggregates every banked
  final into one row per player: games, starts, bench games, DNPs,
  minutes/game, points/game, FGA/min, PF/36, and the mechanism flags
  (capped / cannibal / victim) from the scoring profiles. **No minute
  floor.** Thin samples are flagged (`thin_sample`), never excluded —
  the next eruption candidate is exactly the player a threshold hides.
  First run over 28 banked finals (2026-10-20 → 2026-10-23): **430
  players**, including 54 rostered players with zero minutes yet —
  the returning/inactive watch list no thresholded board can see.
  The thresholded profile layer covered 268 of the 430.
- `research/gameflow/prediction_log.py` — the prospective layer.
  `build --date` freezes named predictions (player + mechanism +
  direction + banked evidence basis) for every game on that date's
  board, before tip. It refuses past dates (no look-ahead) and refuses
  to overwrite an existing log (frozen once written). `grade --date`
  scores the frozen log deterministically against the watcher's final
  game files and writes a sibling `-graded.json`; the original is
  never edited. Mechanisms: FOUL_CAP (DOWN), CANNIBAL (UP), VICTIM
  (DOWN), STEADY (UP). Grading rules are stated verbatim in the module
  docstring; a player who logs under 10 minutes grades NO_DECISION,
  so garbage-time flags can neither fake a hit nor a miss. This layer
  is EVIDENCE only — it carries no pick authority until its own graded
  record earns it.
- `research/gameflow/predictions-2026-10-24.json` — the first frozen
  batch, a real prospective artifact: built 2026-10-24 12:53 UTC,
  first tip 22:00 UTC. 8 games, **53 predictions**: FOUL_CAP 30,
  CANNIBAL 12, VICTIM 10, STEADY 1. 11 entries rest on thin samples
  and are flagged as such in the file. Grades will be appended by the
  grader after tonight's finals (watcher files them independently).
- `research/tests/test_prediction_log.py` — seven deterministic unit
  tests: minute-string parsing (incl. MM:SS and `--`), foul-cap /
  steady / no-decision grading on synthetic finals, cannibal-shape
  detection, and the build command's past-date refusal.

## Verification (local, agency checkout, 2026-10-24)

- `scoring_profiles.py` refreshed: 28 finals, 268 players profiled.
- `full_roster_board.py`: 430 players, 218 thin-sample, 54 DNP-only.
- `prediction_log.py build --date 2026-10-24`: 53 predictions frozen;
  `grade` pre-tip correctly reports all 53 PENDING.
- Unit tests: `python -m unittest discover -s research/tests` — 7/7
  pass in a repo-shaped staging tree (the repo CI command).

## Evidence sources

- ESPN public scoreboard/summary API, via the production watcher
  already contributed in PR #4 (same pipe, same files).
- Agency artifacts: `data/scoring_profiles.json`,
  `data/full_roster_board.json`, `data/predictions/` (agency-local;
  the frozen batch is included here, the board is regenerable from
  the gameflow finals by the included script).

## Limitations (stated, not buried)

- **Name-keyed identity.** Like the rest of the bridge, players are
  keyed by display name + team; there are no stable athlete IDs yet
  (PR #5 documents the same limitation). Same-name collisions across
  teams are separated by the team field; a mid-season trade would
  split a player's rows until an ID layer lands.
- **Daniel Gafford is excluded from VICTIM predictions** in code, with
  the reason recorded: two of his victim flags are the retracted
  pre-hardening detector artifacts for event 401909840 that PR #5
  quarantines. He re-enters when clean games wash the count out.
- **The FOUL_CAP net is deliberately wide** (30 of 53): the owner's
  reach directive prefers flagging everyone and letting grading sort
  it; the <10-minute NO_DECISION rule keeps the record honest.
- Scripts are byte-identical to the agency production copies; their
  data paths resolve relative to the agency checkout. In-repo they are
  the reference implementation plus the frozen artifact, consistent
  with how PR #4 contributed the watcher.

## Security implications

None. Read-only public API, no credentials, no API-contract changes,
no Arena changes, no writes outside `research/`.

## Rollback

Close this PR / delete branch `pax/full-roster-predictions`. Nothing
here modifies `main`, PR #4, PR #5, the shared API contract, or Arena
scoring.
