# Player-prop pretip quote recheck and market-revision audit

**Scope:** Additive, read-only research-only audit. Stacked on PR #21
(original quote-content binding), which depends on PRs #20, #19, #18
and #10. No API-contract edit, prediction/grade overwrite, real-money
execution, production scoring, provider integration, or PR merge.

## Concrete research gap

An original sportsbook quote can be captured and cryptographically bound
before a player-prop selection freezes, then **move, suspend, disappear,
or become stale before tipoff**. The existing original quote-binding
audit can still correctly report `bound`, but that says nothing about
whether the line/price was still offered close to the game.

This matters especially for NBA player props when availability, rotation,
minutes expectations, and injury status change between the morning slate
and tipoff. The original frozen selection **must not be silently replaced
with the favorable side/line that appeared later**.

The implementation is a new independent *pretip* audit. It does not
modify the original frozen quote, historical grading or scoring semantics.

## Records

`research.props.pretip_recheck_audit.PretipMarketRecheck` is a source
declaration for the **same** original quote ID, game, athlete, team,
market, full-game period, over/under side and sportsbook. It carries
one of `open/suspended/withdrawn/unknown`, a source stamp with publication
and capture timestamps and claimed raw SHA-256, and a line/price only
if `open`. Suspended, withdrawn and unknown status may **not** claim
an active price.

`audit_pretip_market_rechecks` accepts the game, **every** frozen
selection, original quotes, archived quote bindings, a collection of
source-stamped rechecks, the pretip review cutoff and two **explicit**
operator-supplied thresholds:

- `max_recheck_age_minutes`: how old the latest recheck can be at cutoff.
- `pretip_window_minutes`: how near tipoff the review cutoff must be.

Both must be integers in 1..240. They are operational choices, not
universal sportsbook standards. An example 15-minute freshness threshold
and 60-minute pretip window are only **synthetic test settings**; this PR
does not impose them on production or claim they are calibrated.

## Integrity behavior

- Original line/side/odds/book/source are validated against the original
  quote-binding fingerprint and archive digest, **not overwritten**.
- Each original frozen selection is retained in the audit denominator.
  Missing, duplicate or ambiguous original quote/binding/recheck data
  fail closed. Extra unselected rechecks and bindings are flagged.
- For repeated market observations, the **latest capture time wins**,
  never the more favorable price. Conflicting observations at exactly
  the same latest timestamp are invalid rather than cherry-picked.
- The latest capture must be after selection freeze, before tipoff,
  available by the pretip cutoff and within the explicit freshness
  threshold. Published-at must not predate the original selection freeze.
- The audit compares the latest quote's market identity, exact line and
  American odds to the original. Status is `unchanged`, `moved`,
  `suspended`, `withdrawn`, `unknown`, `stale`, `missing` or
  `invalid`. A moved quote is a market-change flag, **not** a rewrite
  of the original bet or a model projection.
- Even `unchanged` is a claim of internally consistent source records,
  not independent verification that a bookmaker accepted that price.
  **All source verification, commercial rights and Play flags are false.**

Example synthetic call:

```python
result = audit_pretip_market_rechecks(
    game, selections, original_quotes, bindings, rechecks,
    as_of=review_time,
    max_recheck_age_minutes=15,
    pretip_window_minutes=60,
)
for row in result.rows:
    print(row.selection_id, row.status, row.original_line, row.latest_line)
```

## Tests

```bash
PYTHONPATH=. python -m unittest discover -s research/tests -p 'test_*.py' -v
```

Fixture-only tests cover NBA and NFL, changed lines and prices, suspended
and withdrawn markets, stale rechecks, original binding tampering,
wrong player/team/event/market/book, conflicting latest records,
orphan records, cutoff chronology, and all-original-selection
denominator retention.

**Not tested:** Actual sportsbook market availability, live quote APIs,
official NBA injury feeds, current-season bank completeness, settlement
rules, actual prospective prediction accuracy, website UI or bookmaker
licensing.

## Integration and decisions

- Require authentic point-in-time original quotes and independent
  pretip recaptures from an approved source, with provenance and
  commercial retention rights.
- Choose documented per-sport/per-book freshness and pretip review
  thresholds. Source stamps/digests alone cannot authenticate their
  declared timestamps or content.
- Reconcile with PR #15's cross-sport source revision logic and PR #9's
  market quote readiness before selecting one canonical integration.
- Preserve the owner-required NBA five current-season banked games per
  team before Play, independent defensive and usage analysis, posted
  line sourcing, pretip injury checks, original prediction denominators,
  and immutable historical grading.
- No new Play/Lean decision or scoring authorization is introduced.
  Production promotion, contract changes and merges require owner
  approval and independent review.

Rollback: close this draft PR. The audit makes no network calls or file
writes and adds no dependencies.
