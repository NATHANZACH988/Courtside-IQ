"""Read-only, research-only final-state chronology audit for player props.

A source-stamped "game_final" boolean is not proof that a match ended. This
audit requires a separately supplied event-final receipt with a declared final
time, and refuses player-stat receipts published before that time.

No network, disk writes, official-book settlement or production scoring.
Receipts are structurally checked claims, not independently authenticated.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .observed_outcome import ObservedPlayerStat, compare_observed_stat
from .prop_board import Game, PropQuote, SourceStamp, _id, _utc


@dataclass(frozen=True)
class EventFinalReceipt:
    event_id: str
    home_team_id: str
    away_team_id: str
    final_at: datetime
    source: SourceStamp
    status: str = "final"

    def __post_init__(self) -> None:
        for field in ("event_id", "home_team_id", "away_team_id"):
            _id(getattr(self, field), field)
        object.__setattr__(self, "final_at", _utc(self.final_at, "final_at"))
        if not isinstance(self.source, SourceStamp):
            raise ValueError("final-event source must be a SourceStamp")
        if self.status != "final":
            raise ValueError("only explicit final status is supported")


@dataclass(frozen=True)
class AuditedPropOutcome:
    quote_id: str
    event_id: str
    athlete_id: str
    market: str
    original_line: str
    selected_side: str
    compared_at: datetime
    comparison: str
    structurally_valid: bool
    reasons: tuple[str, ...]
    final_at: datetime | None
    actual_stat: str | None
    # None of these flags may be promoted from merely plausible receipts.
    source_independently_verified: bool = False
    official_book_settlement_verified: bool = False
    scoring_eligible: bool = False
    model_accuracy_established: bool = False


def audit_prop_outcome_final(
    game: Game,
    quote: PropQuote,
    observed: ObservedPlayerStat,
    final_receipt: EventFinalReceipt | None,
    as_of: datetime,
) -> AuditedPropOutcome:
    """Fail closed on a pre-final stat masquerading as a completed game.

    The underlying mathematical comparison is only exposed if the separately
    sourced event-final receipt is chronologically and identity consistent.
    Even a clean result is *not* an authenticated official score or settlement.
    """
    if not isinstance(game, Game) or not isinstance(quote, PropQuote) or not isinstance(
            observed, ObservedPlayerStat):
        raise TypeError("expected Game, PropQuote, ObservedPlayerStat")
    if final_receipt is not None and not isinstance(final_receipt, EventFinalReceipt):
        raise TypeError("final_receipt must be EventFinalReceipt or None")
    cutoff = _utc(as_of, "as_of")
    base = compare_observed_stat(game, quote, observed, cutoff)
    reasons = list(base.reasons)
    final_time = None

    if final_receipt is None:
        reasons.append("event_final_receipt_missing")
    else:
        final_time = final_receipt.final_at
        if (final_receipt.event_id != game.event_id or
                final_receipt.home_team_id != game.home_team_id or
                final_receipt.away_team_id != game.away_team_id):
            reasons.append("event_final_identity_mismatch")
        if final_time <= game.scheduled_start:
            reasons.append("event_final_not_after_start")
        if final_time > cutoff:
            reasons.append("event_final_after_review_cutoff")
        if final_receipt.source.published_at < final_time:
            reasons.append("event_final_published_before_final")
        if final_receipt.source.captured_at < final_time:
            reasons.append("event_final_captured_before_final")
        if final_receipt.source.published_at > cutoff or final_receipt.source.captured_at > cutoff:
            reasons.append("event_final_source_after_review_cutoff")
        if observed.source is not None:
            if observed.source.published_at < final_time:
                reasons.append("player_stat_published_before_event_final")
            if observed.source.captured_at < final_time:
                reasons.append("player_stat_captured_before_event_final")
        elif observed.participation != "unknown":
            reasons.append("player_stat_source_missing")
    if not observed.game_final:
        # Already flagged by base, but kept explicitly as an invalid state.
        pass

    valid = not reasons
    return AuditedPropOutcome(
        quote_id=quote.quote_id, event_id=game.event_id,
        athlete_id=quote.athlete_id, market=quote.market,
        original_line=quote.line, selected_side=quote.side,
        compared_at=cutoff,
        comparison=base.comparison if valid else "invalid",
        structurally_valid=valid, reasons=tuple(dict.fromkeys(reasons)),
        final_at=final_time,
        actual_stat=base.recorded_stat if valid else None,
    )
