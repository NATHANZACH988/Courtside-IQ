# NBA Player-Prop Projection Content and Premarket Archive Audit

**Scope:** Read-only, research-only additive gate stacked on PR #25 (PR #24 →
#23 → #18 → #10). This does not change the shared API contract, existing
prediction grader, historical grades, production scoring, authentication,
market data feeds, or bookmaker settlement logic.

## Reproduced weakness

PR #25 freezes **which athletes and markets were screened** and the
associated decision reasons. It intentionally does not freeze the numeric
projection. A synthetic test modifies a considered NBA points projection
from **22.0 to 30.0** while retaining the original frozen roster-screen
receipt. The PR #25 screen audit still reports `structurally_valid=True`,
because the altered number is not in its manifest hash.

This is a **separate missing gate**, not a defect in PR #25's stated
screen-only scope. It is also **not evidence of actual historical tampering**.

An altered numeric prediction can change apparent model-vs-line value and
the claimed performance of a prop research strategy. Numeric predictions
must be frozen and content-bound independently of roster decisions.

## Additive solution

`research/props/nba_projection_binding_audit.py` provides:

- `nba_projection_content_sha256(game, projection)`: deterministic
  versioned SHA-256 digest of event, scheduled start, both teams, stable
  athlete/team/market, **exact predicted stat**, input cutoff, freeze
  timestamp and supplied raw prediction artifact digest.
- `nba_projection_binding_record_sha256(...)`: versioned digest binding
  that projection hash to the **original frozen full-roster screen hash**.
- `FrozenNBAProjectionReceipt`: declared per-player/market archive receipt,
  including exact prediction and screen hashes and a `SourceStamp`.
- `audit_nba_projection_bindings(...)`: independent read-only audit for
  **every considered player × market**, rejecting missing/duplicate/orphan
  receipts, mutated predictions, changed screen manifests, wrong team/event,
  ambiguous original book/side quotes, quote captures before the projection
  archive, and late or chronologically impossible source records.

The source receipt must claim publication and capture **after the model
projection was frozen** but **before the original sportsbook quote was
captured**, before the pregame review cutoff, and before tipoff. The frozen
roster-screen receipt must precede each projection's original input cutoff.

A screen-only audit that is invalid cannot yield a `bound` projection row.
If no considered players exist, the full-screen audit may still be
structurally valid, but it never authorizes a Play.

### Minimal usage

```python
from research.props.nba_frozen_screen_manifest import nba_screen_manifest_sha256
from research.props.nba_projection_binding_audit import (
    FrozenNBAProjectionReceipt,
    nba_projection_content_sha256,
    nba_projection_binding_record_sha256,
    audit_nba_projection_bindings,
)

screen_digest = nba_screen_manifest_sha256(game, roster, markets, screens)
projection_digest = nba_projection_content_sha256(game, frozen_projection)
archive_payload_digest = nba_projection_binding_record_sha256(
    game, frozen_projection, screen_digest, projection_digest,
)

# archive_source must refer to a genuinely preserved, independently
# authenticated premarket receipt with raw_sha256 == archive_payload_digest.
# Do NOT regenerate the receipt after reviewing outcomes.
receipt = FrozenNBAProjectionReceipt(
    frozen_projection.athlete_id, frozen_projection.team_id,
    frozen_projection.market, screen_digest, projection_digest,
    archive_source,
)
report = audit_nba_projection_bindings(
    game, roster, markets, screens, projections,
    original_screen_receipt, (receipt,), original_quotes,
    pregame_review_cutoff,
)
```

## Security and evidence limitations

This code uses the Python standard library only. It has **no network calls,
filesystem writes, credentials, API routes or external dependencies**.

The SHA-256 hashes only establish **consistency of caller-supplied
records**. The model artifact's raw bytes are not inspected here; its
`artifact_sha256` is itself a claim. The archive receipt, timestamp and
sportsbook source are not independently authenticated. An adversary can
rewrite a projection **and** regenerate the claimed archive receipt; the
audit can then return structurally valid. The regression suite demonstrates
this limitation explicitly.

Every report therefore keeps `external_archive_verified=False`,
`independently_verified_original_predictions=False`,
`prediction_accuracy_established=False`, `scoring_authorized=False`,
and `play_authorized=False`. No probabilities, ROI, real bookmaker
settlements or historical NBA results are asserted.

For actual pregame integrity, archive original model artifacts, their
frozen prediction manifests, and original book quote payloads in
independently timestamped immutable storage. Preserve all revisions and
use the **original** frozen prediction/line for grading. Obtain authorized
provider access and independently verify NBA source provenance.

## Tests

```bash
PYTHONPATH=. python -m unittest discover -s research/tests -p 'test_*.py' -v
```

Synthetic fixtures cover numeric prediction mutation, changed input and
freeze timestamps, artifact digest changes, wrong player/team/event, changed
screen manifest, duplicate/missing/orphan receipts, contradictory original
book quotes, late publication/capture, market quote ordering, no-candidate
screens, multi-market coverage and deliberately regenerated fake receipts.
No real sportsbook data or independent NBA source authentication is tested.

## Integration dependencies and decisions

This PR is stacked on #25 and does **not** integrate sibling player-prop
quote/settlement integrity PRs #19–#22 or Pax's prediction engine PR #6.
A later integration must reconcile **all** gates with their independent
test suites, preserve original immutable manifests, use licensed official
data, and validate prospective performance against frozen baselines.

Owner review is required before merging, changing `docs/API_CONTRACT.md`,
authorizing production scoring or Play classifications, or purchasing
provider access. The five-current-season-banked-games-per-NBA-team rule
remains unchanged.

**Rollback:** Close this unmerged draft PR. Existing historical predictions,
grading semantics, production routes and API contracts are untouched.
