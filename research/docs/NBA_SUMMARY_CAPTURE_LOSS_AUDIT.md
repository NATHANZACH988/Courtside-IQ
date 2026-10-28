# NBA summary capture-loss audit (research only)

## Why this exists

The agency watcher in Pax PR #4 fetches the ESPN NBA summary and then emits a
compact JSON object containing scores, segments, runs, notes and a limited
player box score. It reads plays to calculate runs but does not retain the
underlying play-by-play, clock/shot-coordinate evidence, officials or team
statistics. Its player output also omits assists, threes and other available
box-score fields in the reviewed branch. The agency may have newer local code;
this report concerns **the committed PR #4 watcher only**.

The new `research/capture/nba_summary_capture_audit.py` performs an offline,
read-only comparison of **a caller-supplied raw summary** and **the compact
output for the same event**. It reports which fields actually present in the
source were discarded, partially retained or altered. Missing fields in the
source are `not_in_source`, never falsely reported as dropped.

Checks include:

- Event identity and canonical digest of the *supplied* summary.
- Exact equality of play-by-play, officials and team-statistic arrays when
  they are present on both sides.
- Play-clock and shot-coordinate comparison **bound to unique play IDs**, so a clock or shot location moved to another event is not incorrectly marked retained.
- Partial play-by-play is accepted only for an exact, ordered subset with unique play IDs; fabricated, duplicated, or altered plays are unreconciled.
- Player-level equality for AST, 3PT makes/attempts, STL, BLK, TO and FT
  makes/attempts, matched by team abbreviation plus display name.
- Independent player-identity universe reconciliation: missing source athletes
  are partial/discarded; unexpected captured athletes are unreconciled, even
  when every source athlete's individual stat fields still match. The
  identity section reports matched, missing and unexpected counts.
- Duplicate or missing player identities, partial captures and conflicting
  same-count play data.
- Player-stat reconciliation distinguishes **absent fields** (`discarded`),
  **incomplete or partly retained fields** (`partial`), and **present but
  mismatched/invalid values** (`altered_or_unreconciled`). Per-stat
  `captured_items` counts player rows with at least one supplied field;
  `retained_items`, `partial_items`, and `altered_items` make the
  classification auditable. Any mismatch takes precedence over a partial
  capture; this is not a proof that the source was authentic.

### Example use

```python
import json
from research.capture.nba_summary_capture_audit import audit_nba_summary_capture

with open("raw-summary.json") as f:
    raw = json.load(f)
with open("compact-watcher.json") as f:
    compact = json.load(f)
result = audit_nba_summary_capture(raw, compact)
print(json.dumps(result, indent=2))
```

The audit makes **no network requests**, writes no files, and cannot change
frozen predictions or historical grades. Its tests use entirely synthetic
fixtures, not purported ESPN finals.

## Critical limitations

- The digest is a canonical hash of the *supplied JSON object*, **not** an
  authenticated digest of ESPN's original response bytes or a proof of
  publication/capture chronology. `source_authenticity_verified` is always
  false.
- A section absent from the source is unobservable, not proof of completeness.
  The separate `complete_source_surface_observed` flag remains false.
- The generic summary shape may change. Fields not recognized by this version
  are not checked. The output does not certify comprehensive ESPN coverage.
- Captured play, clock, or shot-coordinate evidence absent from the supplied source is flagged as unreconciled, not authenticated as a valid addition.
- Play IDs are treated as identity keys for this offline diagnostic. Missing or duplicated IDs are classified as unreconciled rather than silently matched; this does not independently authenticate ESPN event identities.
- Player identity uses team + display name, because the committed watcher
  drops ESPN athlete IDs. This is insufficient for durable cross-season or
  traded-player identity. Ambiguous same-team names are rejected. Unexpected
  names are flagged as unreconciled, not automatically declared fabricated:
  differences in naming conventions or partial source payloads require manual
  review.
- No sportsbook line, pricing, calibrated probability, independent source
  verification, provider license, or prospective betting result is produced.
  `player_prop_scoring_authorized` remains false.
- This PR **does not modify the production watcher**. Archiving the original
  bytes with retrieval timestamps and revisions must be implemented separately
  in the agency source and reviewed for storage, retention and provider terms.

## Reproduction

```bash
python -m unittest discover -s research/tests -p 'test_*.py' -v
```

This is an independent PR based on `main`, not a patch to Pax's branches.
No shared API contract, auth code, production scoring or historical grades
are modified. No merge is requested.
