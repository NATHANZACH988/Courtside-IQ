"""Read-only readiness audit for sport-neutral historical market quotes.

This module does not grade bets, infer a winning side, or authorize data use.
The initial MarketQuote schema has no selection side, period, or settlement
rules. Those missing fields must never be silently inferred.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .evidence import Event, MarketQuote, SPORT_MARKETS


@dataclass(frozen=True)
class QuoteReadiness:
    quote_id: str
    point_in_time_replay_ready: bool
    scoring_eligible: bool
    settlement_eligible: bool
    rights_review_required: bool
    reasons: tuple[str, ...]


def audit_quote(event: Event, quote: MarketQuote, as_of: datetime) -> QuoteReadiness:
    """Audit a historical quote without mutating the evidence ledger.

    point_in_time_replay_ready means only that the quote has an event-consistent
    capture chronology and a declared raw-payload digest. It does NOT imply
    valid rights, authenticity, accurate odds, predictive value, or suitability
    for scoring/settlement.
    """
    if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be a timezone-aware datetime")
    cutoff = as_of.astimezone(timezone.utc)
    reasons: list[str] = []
    if quote.event_id != event.event_id:
        reasons.append("event_mismatch")
    if quote.team_id not in (event.home_team_id, event.away_team_id):
        reasons.append("team_mismatch")
    if quote.market not in SPORT_MARKETS[event.sport]:
        reasons.append("market_not_registered_for_sport")
    if cutoff >= event.scheduled_start:
        reasons.append("cutoff_not_pregame")
    if quote.source.published_at > cutoff:
        reasons.append("published_after_cutoff")
    if quote.source.captured_at > cutoff:
        reasons.append("captured_after_cutoff")
    if quote.source.captured_at >= event.scheduled_start:
        reasons.append("captured_at_or_after_start")
    if quote.source.content_sha256 is None:
        reasons.append("raw_payload_digest_missing")

    # These are independent blockers: an internal replay-ready record is not
    # permission to use provider data and is not a settled wagering selection.
    if quote.source.rights != "licensed":
        reasons.append("rights_not_declared_licensed")
    reasons.extend((
        "rights_attestation_not_independently_verified",
        "selection_side_missing",
        "market_period_missing",
        "settlement_rules_missing",
    ))
    replay_blockers = {
        "event_mismatch", "team_mismatch", "market_not_registered_for_sport",
        "cutoff_not_pregame", "published_after_cutoff",
        "captured_after_cutoff", "captured_at_or_after_start",
        "raw_payload_digest_missing",
    }
    return QuoteReadiness(
        quote_id=quote.quote_id,
        point_in_time_replay_ready=not any(x in replay_blockers for x in reasons),
        scoring_eligible=False,
        settlement_eligible=False,
        rights_review_required=True,
        reasons=tuple(reasons),
    )
