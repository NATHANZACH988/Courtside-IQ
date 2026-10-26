# NBA Player-Prop Full-Roster Screening Freeze Audit

**Scope:** Separate read-only research integrity check, stacked on PR #24
(PR #23 → PR #18 → PR #10). Does not edit Pax's engine, existing grades,
production scoring, Arena routes, or the shared API contract.

## Reproduced issue: full-roster screening can be reconstructed after projection

The parent NBA context and frozen game-bank audits validate game history,
role/injury, opponent defense, and quotes at relevant cutoffs. However,
the roster snapshot used to justify the *full player universe* is
checked at board-review time, **not at the model's original input cutoff**.

Synthetic reproduction:

- 09:00 UTC: initial roster source, 10:00–11:00 injury/role sources.
- 12:00 UTC: projection input cutoff; 13:00 UTC: projection freeze.
- 13:00 UTC: replacement roster source (not known at noon).
- 14:00 UTC: quote capture; 15:00 UTC: board review.

Both parent `audit_nba_prop_context` and `audit_nba_frozen_bank`
report context complete, despite the replacement roster having arrived
*after* the model input cutoff. The same problem applies to a bench
player's late-added roster entry: it can be presented as though it
belonged to the original full-roster screening universe.

**This is a synthetic code-level counterexample, not evidence that Pax
or any NBA analyst manipulated historical picks.**

## Additive solution

`research/props/nba_frozen_screen_manifest.py` adds:

1. A canonical `nba-full-roster-screen-v1` JSON representation and
   SHA-256 content digest binding event, scheduled start, both teams,
   requested markets, **all supplied roster athletes** (stable ID, team,
   availability, source details) and **every player-market screening
   decision and reason**.
2. `audit_nba_frozen_screen_manifest` compares the computed digest with
   a separate `SourceStamp.raw_sha256` supplied as the frozen manifest
   receipt. It checks the receipt's captured timestamp against the
   pregame review cutoff and every considered projection's original
   `inputs_as_of`, not merely `frozen_at`.
3. Checks that *all roster entries*, including bench/excluded/unresolved
   players, had source captures no later than the frozen manifest.
4. Checks full declared player × market coverage, duplicate/orphan
   screening records, duplicate/ambiguous projections, wrong team,
   questionable/unknown player handling, and projections without a
   considered screening decision.
5. Keeps separate output fields for content consistency, declared
   full-roster coverage, and independent external verification.

### How to use

```python
from research.props.nba_frozen_screen_manifest import (
    nba_screen_manifest_sha256, audit_nba_frozen_screen_manifest,
)

# Construct game, roster, markets, screens and projections from genuinely
# frozen pregame data; DO NOT reconstruct them from later game results.
# Compute digest when the original manifest is created, then have an
# independently authenticated archive preserve the manifest + digest.
digest = nba_screen_manifest_sha256(game, roster, markets, screens)

# The receipt must be from the original freeze. Computing a NEW receipt
# after changing a prediction/screen is NOT a valid audit.
report = audit_nba_frozen_screen_manifest(
    game, roster, markets, screens, projections,
    original_manifest_receipt, pregame_review_cutoff,
)
```

**Critical:** The digest is only a reproducible fingerprint. A caller
can fabricate timestamps or regenerate both a manifest and its digest
after the fact. A matching digest does **not** prove that the original
player universe was complete, that a sportsbook offered a line, that an
NBA source was official, or that the receipt existed before tipoff.
`external_archive_verified` and
`independently_verified_roster_complete` therefore remain **false**.

For actual independent verification, obtain an authenticated, immutable,
third-party pregame archive with capture timestamps, signed evidence or
equivalent trusted provenance. Preserve the **original** archived
manifest and every superseding revision; never select a favorable
reconstructed subset.

This audit is **supplemental**. A future integration must require all
of PR #24's game-bank gates, PR #23's injury/role/defense gates,
PR #18's player-prop board, PR #22's pretip line recheck, PRs #19–#21's
outcome/quote/denominator protections, and independent provenance before
any production use. This PR does not combine or silently alter those
sibling APIs.

## Tests and limitations

```bash
PYTHONPATH=. python -m unittest discover -s research/tests -p 'test_*.py' -v
```

The new synthetic tests reproduce the upstream late-roster acceptance
and cover late bench entries, late manifest capture, changed decisions,
changed athlete identities and source receipts, omitted bench players,
missing and duplicated screen rows, projection chronology, unknown
availability, exact hash binding, and malformed inputs.

No real NBA games, genuine sportsbook quotes, commercial data licensing,
book-specific settlement rules, or forecasting performance were tested.

**Owner decisions:** Provider access and licensed historical line
archives, externally authenticated frozen manifest storage, and any
eventual shared API/production scoring promotion require separate
approval. The NBA five-current-season-banked-games-per-team minimum
remains unchanged.

**Rollback:** Close this draft PR; all additions are isolated research
files and can be omitted without altering historical grades.
