# NBA player-prop bank snapshots must predate each frozen projection

**Independent research-only review of PR #23.** No shared API contract,
historical grades, production Play/Lean/Pass scoring, or betting advice is
changed by this branch.

## Reproduced issue

PR #23 requires five completed current-season NBA games **per team** and
correctly checks banked-game final/source chronology against the board
review `as_of` cutoff. But the same bank is not checked against each
**considered player's independent projection `inputs_as_of` cutoff**.

A synthetic example reproduces the gap:

- A points projection was frozen using inputs available at **12:00 UTC**.
- One of five purported home-team bank games ended at **13:00 UTC** and
  was captured at **14:00 UTC**.
- The board was reviewed at **15:00 UTC**, before the current event's
  scheduled 20:00 UTC start.
- The parent PR #23 audit reported `context_complete=True` and five
  games per team, even though the model had only **four** home-team
  banked games available at its original input cutoff.

This is a **synthetic code-level hindsight leak**, not evidence of
misconduct or any incorrect historical NBA result. It can overstate
whether a model was adequately informed when the prediction was made.

## Additive correction

`research.props.nba_context_freeze_audit.audit_nba_frozen_bank` runs the
existing parent context audit **without modifying it**, then separately
counts eligible banked games for **both teams for every considered
player-stat projection at that specific projection's `inputs_as_of`**.

The added audit:

- Requires game final, source publication, and source capture to be no
  later than the projection's input cutoff, as well as before tipoff.
- Excludes wrong-season, current-event, duplicate, future and
  invalid-source bank records from the usable count.
- Preserves all player-market rows, including bench, excluded,
  unresolved and missing-screen entries. Zero candidates remain zero.
- Refuses to choose between ambiguous projections, duplicate screen
  records, or mismatched player-team identities.
- Allows more than five bank records in a packet: later records cannot
  justify an earlier projection, but five **genuinely earlier** records
  still meet the threshold.
- Produces per-projection home/away bank counts and explicit failure
  reasons without editing the original projection or result.
- Hard-codes source verification, scoring authorization, and Play
  authorization to `False`.

This audit is **stricter than a review-time five-game floor**: it tests
whether the minimum evidence was actually available to the model at
the original freeze. A late research refresh cannot retroactively
justify an older prediction. It does not establish that the model used
all five games, only that valid receipts were declared as available.

## Reproduction and tests

```bash
PYTHONPATH=. python -m unittest discover -s research/tests -p 'test_*.py' -v
```

`research/tests/test_nba_context_freeze_audit.py` includes a direct
parent-audit counterexample and independent regression tests for
different player cutoffs, later captures, duplicate bank records,
wrong-season/current-event contamination, ambiguous projections,
missing bench screens, zero candidates and fail-closed authorizations.

All inputs are **synthetic**. The code does not download real NBA data,
validate data licensing, authenticate NBA-issued injury reports, verify
actual sportsbook lines, infer probabilities or backtest forecasting
performance. Source URLs, timestamps and SHA-256 values remain
caller-supplied declarations.

## Review, integration and owner decisions

This PR is stacked on **PR #23**, which itself depends on **PR #18**
and **PR #10**. It is independent of PRs #19–#22 and does not reconcile
their original-quote, post-final, denominator or pretip market rules.

Before any production scoring, obtain authenticated immutable
pregame game-bank manifests, official injury/roster and final-stat
feeds, licensed book-specific odds receipts, prospective calibration,
and independent owner approval of integration and scoring semantics.
The owner's **five current-season games per NBA team before Play**
minimum is preserved.

Close this unmerged draft to roll back. No source, production records,
Arena endpoints, shared API contract or historical scores are edited.
