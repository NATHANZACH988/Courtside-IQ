# Frozen player-prop quote content and archive binding audit

**Scope:** Additive, read-only research integrity audit. Stacked on
PR #20 (frozen player-prop denominator), which depends on PRs #19, #18
and #10. No shared API contract changes, production grading, bookmaker
settlement, historical grade edits, network calls or disk I/O.

## Concrete failure mode

The existing `FrozenPropSelection` in PR #20 records a `quote_id`,
`selection_id`, freeze time and an artifact hash claim. It correctly
preserves the supplied denominator, but **does not cryptographically
bind the original selected quote's player, market, side, line, price,
sportsbook or source**. The `artifact_sha256` refers to the original
frozen selection artifact; it is not defined as a hash of the quote
contents. Replacing a postgame `PropQuote` with a different line or
side under the same `quote_id` can change a mathematical matched/missed
classification without triggering the original frozen batch audit.
This is a synthetic code-path weakness, not evidence of actual historical
tampering.

## What this audit adds

`research.props.quote_binding_audit` defines:

- `quote_content_sha256(quote)`: deterministic SHA-256 over canonical
  JSON with a versioned schema tag, including exact original quote ID,
  event/athlete/team IDs, market, period, over/under side, decimal line
  *string*, American odds, sportsbook, and the original provider source
  URL, publication/capture timestamps, raw-payload digest claim and
  rights label.
- `binding_record_sha256(selection_id, quote_id, frozen_at,
  quote_sha256)`: deterministic SHA-256 of a canonical frozen binding
  record. This is the exact payload hash the binding archive must
  declare in its `SourceStamp.raw_sha256`. **An external immutable
  pregame anchor is still required to trust that declaration.**
- `FrozenQuoteBinding`: selection ID, original quote ID, frozen
  selection timestamp, original quote fingerprint, and a claimed
  archive source stamp for the canonical binding record.
- `audit_frozen_quote_bindings`: checks **every supplied selection**
  against exactly one binding and one original quote. It detects changed
  quote contents, quote/selection ID swaps, duplicated IDs, missing
  or orphaned bindings, inconsistent frozen timestamps, wrong event,
  wrong team, unsupported sport market, and sources/archives that
  could not have existed by the claimed freeze and tipoff.

A missing binding produces an `invalid` row, never a silently dropped
selection. Extra orphan bindings invalidate the batch without expanding
the original denominator. Each row is `bound` or `invalid`.
All source-verification, scoring and bookmaker-settlement flags remain
false. A bound row is **not** a winning bet or a verified source.

## Example workflow

1. **Before tipoff:** independently capture the original book quote,
   source bytes, original quote source receipt, and frozen selection.
2. Calculate the canonical `quote_content_sha256`, then the
   `binding_record_sha256` from the original selection ID, quote ID
   and freeze timestamp.
3. Archive that canonical binding payload in an immutable, externally
   timestamped source; retain a `SourceStamp` whose
   `raw_sha256` matches the binding payload hash. The archive must
   be captured after the quote and no later than the selection freeze.
4. **After game:** supply the original frozen selection manifest,
   original quote records, binding records and review cutoff to
   `audit_frozen_quote_bindings`.
5. Only if the quote binding is internally consistent should an
   independent review proceed to PR #20's final-stat/denominator audit.
   Even then, **do not** promote any result to Play/Lean, official
   settlement or scoring without separate evidence and authorization.

## Test command

```bash
PYTHONPATH=. python -m unittest discover -s research/tests -p 'test_*.py' -v
```

The synthetic tests exercise line/side/price/book/athlete/team/source
tampering, exact decimal serialization, pregame archive chronology,
missing and duplicate binding rows, stable cross-sport quote keys,
wrong-event contamination and denominator retention.

## Limits and security

The canonical SHA-256 **detects mismatches between supplied records**;
it cannot prove that any claimed archive or quote existed before tipoff.
A dishonest caller can regenerate every digest and falsify every
timestamp. The audit does not fetch URLs, verify signatures, validate
book licensing, independently confirm raw payloads, or establish
manifest completeness. An externally verifiable immutable pregame
commitment, provider rights, real source bytes and official settlement
rules are required before using the result as historical betting
evidence.

The original `FrozenPropSelection.artifact_sha256` remains unchanged;
the new quote fingerprint is deliberately separate. No data is
automatically collected or written. No API contract, Arena auth, NBA
grading logic, or production scoring is edited. No PR is merged.
Rollback is to close this unmerged draft PR.

## Owner decisions before integration

- Approve a licensed historical book-quote and official game-final
  provider, with source receipts and permissible retention rights.
- Choose an independently timestamped immutable archive mechanism
  (and a canonical record schema version) for original quote bindings.
- Review the PR #10 → #18 → #19 → #20 dependency chain before merging
  or changing any shared API contract.
- Preserve the NBA current-season **five banked games per team** floor
  for Play, original frozen prediction denominators, and prospective
  model-vs-baseline tests. No change to that policy is proposed here.
