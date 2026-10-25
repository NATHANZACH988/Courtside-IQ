# Multi-sport point-in-time research foundation

**Status:** research-only adapter scaffold. No production scoring, wagering recommendations, API changes, data-provider access, or ticket scraping.

This layer is independent of pending NBA research PRs and the provisional shared API contract. It supports normalized event IDs, immutable source stamps, pregame observations, and historical sportsbook quote records when sourced externally.

## Initial sport vocabularies

| Sport | Supported example markets |
| --- | --- |
| NBA | points, rebounds, assists, threes, minutes |
| NFL | passing_yards, rushing_yards, receiving_yards, receptions, passing_tds |
| MLB | hits, total_bases, strikeouts, pitcher_strikeouts |
| NHL | shots_on_goal, goals, assists, saves |
| SOCCER | shots, shots_on_target, goals, assists |

These are illustrative supported stat keys, not complete market catalogs. Period rules, settlement, overtime treatment, alternate lines, and real provider mappings all require their own research and validation.

## Offline fixture demonstration

~~~python
from datetime import datetime, timezone, timedelta
from research.core import EvidenceLedger, Event, MarketQuote, SourceProof

start = datetime(2026, 10, 25, 20, 0, tzinfo=timezone.utc)
ledger = EvidenceLedger()
ledger.add_event(Event("NFL", "nfl:fixture-001", start, "team:home", "team:away"))
source = SourceProof(
    provider="Fixture source",
    source_url="https://example.org/fixture/001",
    published_at=start - timedelta(hours=3),
    captured_at=start - timedelta(hours=2),
)
ledger.add_market_quote(MarketQuote(
    quote_id="fixture:q1",
    event_id="nfl:fixture-001",
    athlete_id="fixture:athlete-12",
    team_id="team:home",
    market="passing_yards",
    line=250.5,
    american_odds=-110,
    sportsbook="Fictional Example",
    source=source,
))
snapshot = ledger.pregame_as_of("nfl:fixture-001", start - timedelta(hours=1))
assert len(snapshot.market_quotes) == 1
assert snapshot.scoring_eligible is False
~~~

The example contains no real sportsbook lines or player identities.

## Integrity invariants

1. Provider-qualified IDs are required; names cannot serve as join keys. Event IDs also carry sport prefixes.
2. Times must be timezone-aware and are normalized to UTC. Pregame replay cutoff must strictly precede scheduled start.
3. Published and captured timestamps must both precede the requested historical cutoff. A retroactive historical publication date alone cannot establish point-in-time availability.
4. Pregame observations and quotes captured at/after start are rejected. Postgame records are excluded from all pregame snapshots.
5. Duplicate records and cross-event team mismatches fail closed. This does not independently establish historical roster affiliation.
6. Quotes preserve market, line, American odds, sportsbook, source URL, and timestamps; no settlement or expected return is inferred.
7. Source rights default to unverified. Licensed/restricted labels are declarations requiring documentation, not entitlement checks.
8. The immutable research snapshot scoring_eligible flag is always false, protecting existing scoring gates.

## Important limitations

- In-memory reference only: no persistence, feeds, auth, prediction scoring, or permission to redistribute data.
- Source times are declared metadata, not independently certified. Before backtesting, persist raw snapshots and collection times in an independently auditable system with integrity hashes.
- Scheduled starts are caller-provided, not authenticated. Postponements and changed tipoffs require a separate event-versioning and lock policy.
- Stable player IDs and team membership still require authoritative, time-specific crosswalks.
- No research artifact can bypass the five-current-season-games-per-team NBA Play gate or other owner-specified sports gates.
- Market price histories need licensed or otherwise permissible collection sources, verified as-of timestamps, and settlement conventions. Winning tickets alone have selection bias.

## Next implementation increments

1. NFL adapter consuming verified, rights-reviewed source captures with historical athlete/team identities.
2. Raw payload digest and append-only correction log, persisted with collection timestamp.
3. Fixture-based multi-sport retrospective replay and walk-forward checks.
4. Historical prop odds-provider coverage and license audit. Ticket discovery only after baseline market-universe and losing-outcome coverage exist.

## Validation and rollback

Run: python -m unittest discover -s research/tests -p 'test_*.py' -v

These fixture tests validate input schema and time barriers, not forecasting quality or profitability. Existing GitHub CI already runs research tests. No external commands, URLs, or credentials are used in the implementation. Close the unmerged PR to roll back; changes do not touch the existing API contract, Arena scoring, or Pax branches.
