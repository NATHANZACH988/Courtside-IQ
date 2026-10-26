# NBA player-prop context gates: bank, injury, role and defense

**Research-only.** This PR adds a separate, read-only NBA evidence audit
to the multi-sport player-prop board in PR #18. It does not edit the
shared API contract, Arena, Pax's gameflow predictions, existing grades,
probabilities, Play/Lean/Pass semantics, or sportsbook integrations.
No network calls, file writes, dependencies, or production promotion.

## Problem being addressed

A full-roster screen and genuine timestamped player-prop line are necessary
but not sufficient to interpret an NBA player prop. The user's NBA
research protocol requires at least **five current-season banked games
for each team** before any Play, player-specific injury and expected
minutes/rotation analysis, and **opponent defense analyzed as its own
evidence layer**. Those inputs must have been known when the original
projection was made, not backfilled from the result.

The audit does not claim that a threshold of five games is sufficient
for a calibrated prediction. It is a minimum owner-required research gate.

## Input records

`audit_nba_prop_context` receives the existing `Game`, complete
`RosterAthlete`, player-stat market universe, `PropScreen`,
`PropProjection`, and `PropQuote` records, plus:

- `BankedGameEvidence`: a distinct NBA event per team, declared
  `YYYY-YY` season, final timestamp and source receipt. Duplicates,
  wrong-season games, the current event, future finals and impossible
  source chronology cannot increase the team bank. The output counts
  **both** teams separately and requires five each.
- `PlayerRoleEvidence`: stable player/team IDs, injury status and
  source-kind claim (`official_report` or `unverified`), a separately
  sourced expected-minutes estimate and rotation role. An eligible
  considered player requires status `available`, a declared official
  report, known role, nonzero expected minutes, and both sources known
  before the projection's recorded input cutoff. `probable`,
  `questionable`, `doubtful`, `out` and `unknown` remain blocked
  until independently resolved. Expected minutes are **assumptions**,
  not official guarantees; no invented minutes threshold is used.
- `OpponentDefenseEvidence`: opponent team, exact player-stat market,
  full-game period, observed sample size, allowance rate, methodology,
  independence declaration and source receipt. Defense must be
  independently documented and known before the projection's input
  cutoff. This is **standalone evidence**, not an arbitrary positive or
  negative probability adjustment.

The audit produces one row for **every rostered athlete × requested
player-stat market**, even for excluded, unresolved or missing screens.
It never restricts the denominator to winners, starters, high-minute
players, or athletes with published lines. Missing real posted quotes
for considered players are explicit blockers; no line is fabricated.

## Output and interpretation

`NBAPropContextAudit` reports per-team bank counts, every player-market
row, context faults and board structural validity. `context_complete`
means the supplied evidence packet is internally complete under these
rules; it does **not** prove the data is authentic, the opponent defense
sample is representative, the injury report is truly official, or the
projection is accurate.

**All results explicitly set**
`sources_independently_verified=False`,
`probability_calibrated=False`, `scoring_authorized=False`, and
`play_authorized=False`, even when all context checks pass.

Source URLs, provider names, source timestamps, rights labels and SHA-256
digests are **claims supplied by the caller**. They are not externally
verified by this audit. A self-declared `official_report` is not proof
of an NBA-issued injury report. This audit does not fetch or cache any
NBA, sportsbook or commercial data.

## Test command

```bash
PYTHONPATH=. python -m unittest discover -s research/tests -p 'test_*.py' -v
```

Synthetic tests cover both team banks, duplicate/mislabeled finals,
wrong-season records, injury status asymmetry, role and minutes,
defense-source independence, future information leakage, missing
posted lines, bench-player coverage, multi-market accountability, and
zero-candidate cases. These tests are **not** historical backtests,
verified NBA evidence, or measured forecasting lift.

## Integration and review decisions

1. Authenticate official NBA game finals, game-day rosters and injury
   reports, and record source receipt/capture provenance and corrections.
2. Establish the actual current-season bank per team. A count of five
   records is only as reliable as the records supplied.
3. Keep pretip injury changes and minutes/role updates separate from
   the original frozen projection; a newer context snapshot cannot
   retroactively justify an older forecast.
4. Independently test opponent defense against a frozen usage/option
   baseline, ideally using PR #14's prospective paired evaluation.
5. Coordinate with the separate pretip market recheck in PR #22,
   original quote binding in PR #21 and denominator audit in PR #20
   **after** independent reviews. This PR intentionally does not
   import those branches, to avoid modifying their semantics.
6. Before any production Play/Lean scoring, obtain approved providers,
   real posted lines and market rights, rulebook-specific settlement,
   independently authenticated snapshots, sport-specific calibration
   and explicit owner authorization.

**Dependency:** draft PR based on PR #18, which depends on PR #10.
It is a sibling to the #19→#22 integrity stack. No shared API
contract edits or merges. Close this unmerged PR to roll back.
