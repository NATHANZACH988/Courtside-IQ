# Player-prop research board and original-line audit

**Scope:** Research-only player-prop data preparation and mechanical result
comparison. Works with NBA, NFL, MLB, NHL, and soccer *market vocabularies*;
this is **not** a licensed provider adapter, a calibrated prediction model,
a wagering service, or production scoring.

This branch is stacked on PR #10's evidence-to-release process, independent
of Pax PRs #4/#6, Arena PR #1, multi-sport evidence PR #8, and the sibling
historical market audit PR #9. It does not edit the provisional shared
`docs/API_CONTRACT.md`, and makes no assumption that the above branches
are already integrated.

## Why player props need their own evidence lane

Player-prop research requires more than a team score or an opinion that a
player's usage is rising. It needs a verified game-day player universe, a
frozen **independent** projection for *each considered player-stat*, an
original book/side/line/price at a point in time, and later a sourced
statistic that belongs to the **same player, team, event, market and period**.

Pax's Oct 24 prediction and game-flow research revealed name-only joins,
late-freeze risks, and grading caveats (see PRs #6, #16 and #17). This
module provides a sport-neutral alternative boundary without changing his
original frozen grades or production grading rules.

## 1. Full-roster prop board

`research.props.prop_board.audit_prop_board` takes:

- `Game`: sport-scoped event ID, two opposing team IDs, scheduled tipoff;
- `RosterAthlete`: provider-qualified stable athlete and event-team IDs,
  active/out/questionable/unknown availability, original source stamp;
- `markets`: requested sport-specific player-stat markets; 
- `PropScreen`: exactly one reason-coded decision for **every rostered
  player × requested market** (`consider`, `exclude`, or `unresolved`);
- `PropProjection`: frozen, independent numeric projection and raw artifact
  digest for each considered player-market; model inputs must predate freeze;
- `PropQuote`: *actual externally captured* original line (stored as an
  exact decimal string), book, over/under side, American odds, explicit
  `full_game` period, event/player/team IDs, timestamped source and digest;
- `as_of`: the explicit pregame research cutoff.

For each sport, sample registered market keys include NBA
`points/rebounds/assists/threes/blocks/steals`, NFL
`passing_yards/rushing_yards/receiving_yards/receptions/passing_tds/rushing_tds`,
MLB `hits/total_bases/pitcher_strikeouts`, NHL
`shots_on_goal/saves/goals/assists`, and soccer
`shots/shots_on_target/goals/assists`. These keys are **provisional
research taxonomies**, not shared API contract changes, league-specific
official settlement definitions, or proofs that any sportsbook actually
offers a corresponding market.

The board rejects duplicate player-market rows, wrong teams, unknown
markets, missing projections, source information acquired too late, and
same book/side duplicate quotes. It reports gaps in market coverage
without inventing missing odds. Zero qualified candidates is valid.

A player with unknown or questionable availability remains `unresolved`,
not an assumed inactive/active pick. Only a rostered `active` athlete
may be `consider`. All other statuses and reasons remain in the full
screening ledger.

The optional `PropComparison.model_minus_line` is a simple **difference
in stat units**, not a hit probability, expected value, profit estimate,
ranking, confidence, or bet recommendation. It is computed only where
the model projection was frozen **before** the original sportsbook
observation. The projected stat itself is never overwritten by the line.

## 2. Compare original posted lines to final facts — NOT book settlement

`research.props.observed_outcome.compare_observed_stat` accepts the
original `Game` + `PropQuote`, an `ObservedPlayerStat` with stable
event/player/team/market/period IDs and sourced final observation, and a
postgame cutoff.

- If the final stat is mathematically greater/less than the original line,
  it reports whether the selected over/under direction agrees or loses.
- Exactly equal is a mathematical `push`, **not independently verified
  sportsbook settlement**.
- DNP returns `dnp_needs_rules`; it does not assume a win, loss or void.
- Unknown participation or unfinished games remain unresolved/invalid.
- Missing or late source receipts, altered event/team/athlete identity,
  mismatched sport markets and post-tip quote captures fail closed.

The module makes **no ROI, win-rate, or betting-edge claim**. Real
sportsbooks may differ on settlement periods, qualification/participation,
overtime, dead heats, stat corrections, cancellations and voids. That
requires a separately versioned official rulebook/settlement feed and
owner review; none is invented here.

## 3. Evidence and authorization rules

`SourceStamp` requires: provider, HTTPS URL without embedded credentials,
UTC-aware publication and capture times, SHA-256 raw-payload digest *claim*
and explicit `unverified`/`restricted`/`licensed` rights label.

Publication/capture times and digests are not independently authenticated.
`licensed` is a user-supplied label, not independent permission to
redistribute data. Provider data rights and real market availability
remain outstanding. Game-day roster proof and official event start must
be independently captured.

**All returned boards and observed outcomes hard-code production Play,
scoring and book-settlement authorization to false.** Keep the current
NBA owner rule of five current-season banked games per team before Play,
full-roster opportunity screening, official injuries, archived posted
lines and original frozen prediction grading. NFL/MLB/NHL/soccer need their
own validated gating thresholds.

## 4. Test command

```bash
PYTHONPATH=. python -m unittest discover -s research/tests -p 'test_*.py' -v
```

These are **synthetic regression tests** covering NBA/NFL/MLB/NHL/soccer
market vocabularies, every-player coverage, quote identity, chronology,
source rights labels, unknown availability, DNP/push treatment, exact
decimal lines, and manipulated identity/source records. They are not
historical-game backtests and use no sportsbook API or owner secrets.

## 5. Next integration steps (not included in this PR)

1. Capture a genuine game-day full player roster with source receipts and
   stable IDs rather than reconstructing today from banked historical games.
2. Connect the proposed sport-neutral market ledger (#8/#9) through a
   **reviewed adapter**; do not modify `docs/API_CONTRACT.md` unilaterally.
3. Import and independently grade Pax's full 53 original frozen research
   hypotheses, preserving unchanged historical grades and supersessions.
4. Build a permissioned historical odds provider adapter recording both
   sides, prices, original observation times and book-specific periods/rules.
5. Add independent opponent-defense and player-role mechanisms, and test
   whether they improve **prospectively frozen** baselines via PR #14.
6. Add sport-specific, independently validated settlement and play
   eligibility rules only after review and owner approval.

**Rollback:** close this unmerged draft PR. No existing historical records,
production scoring, database, Arena routes, auth or shared API contract
are changed by these files.
