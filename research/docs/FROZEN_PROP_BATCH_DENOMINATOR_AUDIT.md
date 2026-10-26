# Frozen player-prop batch denominator audit (research only)

## Reproducible risk and objective

PR #18 compares posted player-prop lines to observed stats; PR #19
requires a separately sourced event-final receipt before a per-leg
comparison can be labeled mathematically successful. Both are useful,
but a per-leg checker alone cannot identify a **winners-only batch**
assembled after a game or preserve the number of original misses and
unresolved player props. A downstream report could show only favorable
legs and make an unsupported hit-rate claim even if every reported
individual leg passed its source chronology checks.

This branch adds an optional, **read-only full-denominator audit**.
It does not change either existing comparison function, the NBA grader,
historical results, the shared API contract, or production scoring.

## Inputs

Call `research.props.frozen_batch_audit.audit_frozen_prop_batch` with:

1. One `Game`, and a **declared original complete frozen** tuple of
   `FrozenPropSelection` rows. Each row identifies a selection and the
   **exact quote ID**, the declared freeze time and a SHA-256 manifest
   artifact digest claim.
2. The immutable original `PropQuote` records, each with actual
   sportsbook, side, price, line, market, period, event/player/team IDs,
   pregame publication/capture timestamps, source URL and digest claim.
3. Source-stamped `ObservedPlayerStat` rows, including explicit DNP
   or unknown participation, and the independently *supplied*
   `EventFinalReceipt` from PR #19.
4. A timezone-aware postgame `as_of` cutoff.

No outcome or quote is fetched, synthesized or backfilled by this audit.

## Results and invariants

- The **denominator is always the number of supplied frozen selections**,
  never the number of winners, matched source records or successful legs.
- Every selection gets one row in original input order. Missing quotes
  are `invalid`; missing final player stats are `pending`, not a loss.
- Duplicate selection IDs or reuse of one quote ID for multiple
  selections are invalid, not double-counted wins.
- Original quote must exist uniquely, match the event and its teams,
  and have been captured before the selection was frozen and before tip.
  Post-tip or post-cutoff freezes are invalid.
- Player stats join on exact event, stable athlete ID, team ID, market
  and period. **Duplicate or conflicting final stat receipts are
  ambiguous** and invalid until versioned correction rules exist; the
  audit never picks the more favorable value.
- The underlying PR #19 final chronology audit must pass for any
  directional comparison to be reported.
- DNP needs bookmaker-specific rules, pushes are separate from
  directional matches, unknown participation stays unresolved.
- Extra observed stats are counted separately and explicitly excluded
  from the frozen denominator. No opportunistic selection from them.
- A structurally valid report may still contain pending, DNP or unknown
  rows. That does **not** mean it is eligible for a betting pick,
  official settlement or model-performance claim.

The audit reports counts for `direction_matched`,
`direction_missed`, `pending`, `invalid`, `pushes`, and
`dnp_needs_rules`. It **does not** calculate a win rate, ROI, expected
value, or recommend any prop. All trust, settlement and production
scoring flags are hard-coded false.

## Evidence limitations and integration decisions

This does **not** authenticate that the supplied manifest is the
actual original pregame selection universe. The SHA-256 values and
timestamps are caller-declared; independent immutable storage,
source-receipt verification, provider licensing and archive completeness
checks remain required. `manifest_completeness_verified=False` is
intentional. A caller could still omit losing selections *before*
supplying the manifest; this cannot be solved from a per-batch file.

To make NBA player-prop research auditable end to end:

- Verify complete official game-day rosters and original lines using
  licensed/authorized provider captures and stable athlete IDs.
- Freeze an entire player/market opportunity universe before tip, not
  only selected winning-looking quotes; preserve excluded and unresolved
  opportunities separately in PR #18's full-roster screen.
- Store manifest and quote digests in immutable independently timestamped
  storage; maintain correction/supersession lineage for player stats.
- Pair prospective frozen predictions against naive and market
  baselines (PR #14), retaining missing/push/DNP counts and never
  substituting reconstructed postgame prices.
- Apply the owner's NBA five current-season banked games per team
  minimum before any Play recommendation. This audit never promotes Play.
- Obtain approval before any shared API contract edit, bookmaker
  settlement policy, model scoring change, data provider spend, or merge.

## Synthetic test command

```bash
PYTHONPATH=. python -m unittest discover -s research/tests -p 'test_*.py' -v
```

Tests use invented event/player/quote identifiers, lines and statistics.
They are **not** historical NBA backtests, actual sportsbook verification
or evidence of a profitable model. No third-party dependencies, network
calls, disk writes or secrets are required.

## Dependency and rollback

Draft PR is stacked on PR #19 (which depends on PR #18 and PR #10).
It adds only `research/props/frozen_batch_audit.py`, synthetic tests and
this document. Close the unmerged PR to roll back. No historical grades,
Arena auth/routes, production scoring or shared API contract are touched.
