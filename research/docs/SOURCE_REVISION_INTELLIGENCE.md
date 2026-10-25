# Source revision intelligence — point-in-time evidence, contradictions, retractions

**Research-only additive component.** This is an information layer for NBA,
NFL, MLB, NHL, and soccer. It does not fetch data, assert commercial
permissions, rewrite frozen predictions, or modify `docs/API_CONTRACT.md`.

## Why it matters

Sports source data changes. A player can be initially listed questionable,
subsequently marked out, or corrected after a game. Injury pages, official
lineups, box scores, coaching observations, and historical market feeds may
disagree. If the current value is joined onto an old prediction, the result is
hindsight contamination.

`research.quality.source_revisions.SourceRevisionLedger` preserves **every
observed source revision as its own frozen record**. A requested as-of
time only sees information that the source claims was **both published and
captured** by that cutoff. A later correction cannot rewrite an earlier
view. A withdrawn observation disappears from current active evidence, but
the history and old as-of view remain accessible.

## API (internal Python library, not an HTTP contract)

- `EventClock(sport, event_id, scheduled_start, home_team_id, away_team_id)`:
  event and scheduled-start context with qualified event/team IDs.
- `SourceRevision`: unique revision/series/event/entity IDs, sport, metric,
  provider, active or withdrawn state, typed fact (or a withdrawal tombstone),
  source URL, published/captured/effective timestamps, raw SHA-256 **claim**,
  rights status, game-scoped team, and predecessor revision ID.
- `SourceRevisionLedger.add_event`, `add_revision`, `history(series_id)`:
  enforce independent provider-series keys, monotone capture times, explicit
  predecessor references, same-event/team/sport validation and append-only
  history.
- `as_of(event_id, cutoff, pregame=True, max_age_seconds=None)`: immutable
  view of facts known by a strict pre-start cutoff, withdrawn series,
  disagreements by event/entity/metric, athlete team conflicts, and optionally
  stale evidence at a **caller-declared** age threshold.

This is an in-memory reference implementation. Reproducible durable storage,
authenticated receipt capture, source contracts, real provider adapters, and
provider-defined field semantics need separate reviewed work.

### Illustrative use (synthetic, not a real injury report)

```python
from datetime import datetime, timezone
from research.quality.source_revisions import EventClock, SourceRevision, SourceRevisionLedger

utc = lambda hour: datetime(2026, 10, 25, hour, tzinfo=timezone.utc)
ledger = SourceRevisionLedger()
ledger.add_event(EventClock("NFL", "nfl:example-001", utc(20), "team:home", "team:away"))
ledger.add_revision(SourceRevision(
    revision_id="receipt:first", series_id="feed:injury-status",
    sport="NFL", event_id="nfl:example-001", entity_id="athlete:example",
    metric="injury_status", provider="synthetic-feed", state="active",
    value="questionable", team_id="team:home",
    source_url="https://example.org/fake-injury-feed",
    published_at=utc(13), captured_at=utc(14), effective_at=utc(20),
    raw_sha256="a" * 64, rights_status="unverified",
))
snapshot = ledger.as_of("nfl:example-001", utc(19))
assert snapshot.active_revisions[0].value == "questionable"
assert not snapshot.scoring_eligible
```

If a later source revision says `out` and supersedes
`receipt:first` after kickoff, the original 19:00 research snapshot is
still `questionable` and the later retrospective view is `out`.

## Important semantics / limitations

- **Availability is not effective date.** A source's `effective_at` may
  describe a past or future event but cannot establish when the record
  was available. Published **and** captured timestamps control as-of views.
- **Reported capture times and digests are unverified.** Raw hashes in this
  module are syntactically checked, not recomputed from original evidence,
  signed by an independent time authority, or tied to an immutable storage
  layer.
- **Rights are declarations.** A `licensed` label is not independently
  validated permission; `provenance_independently_verified=False` and
  `scoring_eligible=False` stay false for *every* view.
- **Disagreements are explicit, not arbitrated.** Different providers may
  disagree about an injury, anticipated playing time, or team affiliation.
  The engine does not take a majority vote or privilege its preferred source.
  A numerical 20 equals 20.0, but string "20" is not a numeric 20.
- **Retractions preserve old records.** A withdrawal is an explicit
  superseding tombstone, not a deletion. It does not change a previously
  frozen snapshot.
- **Scheduled start is not automatically authenticated.** The event start is
  supplied by the caller. Live schedule changes and source freshness
  require independently captured event-clock revisions and more tests.
- **Research eligibility remains separate.** NBA's five-current-season-games-
  per-team Play gate, full-roster screen, point-in-time lineup evidence,
  market snapshot sourcing, and the multi-sport validation protocol are
  NOT implemented or bypassed here.
- **Not a real market feed.** No odds ingestion, ticket verification,
  scraping, wagers, settlement, or positive-edge claims.

## Integration opportunities (not yet implemented)

1. Pair the sport-neutral ledger in draft PR #8 with
   source history on field changes. Keep its existing types as-is until
   dependency and API contract review.
2. Require Pax's prospective prediction and injury/lineup handoffs to store
   raw receipts and link prediction context to `revision_id`, rather than
   display-name-based joins or a mutable latest-state lookup.
3. Compare today-vs-history conditions using **their original known-at-time
   evidence**, not today's corrected injuries or later market close.
4. Build an official/provider adapter per sport after rights and capture
   limitations are verified. Maintain source versioning and a release-safe
   correction trail.
5. Add negative examples to our prediction bank when a strong-looking
   research hypothesis was driven by a source disagreement or late update.

## Validation

```bash
PYTHONPATH=. python -m unittest discover -s research/tests -p 'test_*.py' -v
```

The tests use **synthetic historical scenarios** only. They do not establish
actual NBA/NFL predictive skill, sportsbook profitability, or commercial
permission to use any third-party source.
