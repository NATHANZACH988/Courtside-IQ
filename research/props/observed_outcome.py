"""Research-only comparison of *posted* player-prop sides to observed stats.

NOT a sportsbook settlement engine. Does not assume DNP void rules, calculate
profitability, or establish an offered price, data rights, or bet acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from .prop_board import (
    Game, PropQuote, SourceStamp, SPORT_MARKETS, _id, _positive_stat, _utc,
)


@dataclass(frozen=True)
class ObservedPlayerStat:
    """An explicitly sourced player stat, DNP, or unresolved outcome."""
    event_id: str
    athlete_id: str
    team_id: str
    market: str
    period: str
    participation: str  # played, dnp, unknown
    actual_stat: str | None
    game_final: bool
    source: SourceStamp | None

    def __post_init__(self) -> None:
        for field in ("event_id", "athlete_id", "team_id"):
            _id(getattr(self, field), field)
        if not isinstance(self.market, str) or not self.market.strip():
            raise ValueError("market required")
        if self.period != "full_game":
            raise ValueError("period must be full_game")
        if self.participation not in {"played", "dnp", "unknown"}:
            raise ValueError("participation must be played, dnp, or unknown")
        if type(self.game_final) is not bool:
            raise ValueError("game_final must be a boolean")
        if self.participation == "played":
            _positive_stat(self.actual_stat, "actual_stat")
        elif self.actual_stat is not None:
            raise ValueError("DNP and unknown cannot assert an actual stat")
        if self.participation in {"played", "dnp"} and not isinstance(
                self.source, SourceStamp):
            raise ValueError("resolved outcomes require a source receipt")
        if self.source is not None and not isinstance(self.source, SourceStamp):
            raise ValueError("invalid source receipt")


@dataclass(frozen=True)
class PropOutcomeComparison:
    quote_id: str
    event_id: str
    athlete_id: str
    market: str
    compared_at: datetime
    structurally_valid: bool
    comparison: str  # selected_over, selected_under, push, dnp_needs_rules, unresolved, invalid
    recorded_stat: str | None
    original_line: str
    selected_side: str
    reasons: tuple[str, ...]
    official_book_settlement_verified: bool = False
    source_independently_verified: bool = False
    scoring_eligible: bool = False
    model_accuracy_established: bool = False


def compare_observed_stat(
    game: Game, quote: PropQuote, observed: ObservedPlayerStat,
    as_of: datetime,
) -> PropOutcomeComparison:
    """Compare an original line and side against a *claimed* final statistic.

    An 'over'/'under' comparison only reports mathematical agreement between
    the stat and the posted line; it is NOT verified betting settlement.
    """
    if not isinstance(game, Game) or not isinstance(quote, PropQuote) or not isinstance(
            observed, ObservedPlayerStat):
        raise TypeError("expected Game, PropQuote, and ObservedPlayerStat")
    cutoff = _utc(as_of, "as_of")
    reasons: list[str] = []
    if cutoff <= game.scheduled_start:
        reasons.append("outcome_review_before_event_start")
    if quote.event_id != game.event_id or observed.event_id != game.event_id:
        reasons.append("event_identity_mismatch")
    if quote.athlete_id != observed.athlete_id or quote.team_id != observed.team_id:
        reasons.append("athlete_team_identity_mismatch")
    if quote.team_id not in {game.home_team_id, game.away_team_id}:
        reasons.append("quote_team_not_in_event")
    if (quote.market != observed.market or quote.period != observed.period or
            quote.market not in SPORT_MARKETS[game.sport]):
        reasons.append("market_period_mismatch")
    if (quote.source.published_at > quote.source.captured_at or
            quote.source.captured_at >= game.scheduled_start or
            quote.source.captured_at > cutoff):
        reasons.append("quote_not_known_before_event")
    if not observed.game_final:
        reasons.append("game_not_confirmed_final")
    if observed.source is not None:
        if observed.source.published_at > cutoff or observed.source.captured_at > cutoff:
            reasons.append("outcome_source_after_review")
        if observed.source.captured_at <= game.scheduled_start:
            reasons.append("outcome_source_before_event_start")
    elif observed.participation != "unknown":
        reasons.append("outcome_source_missing")

    valid = not reasons
    outcome = "invalid"
    if valid and observed.participation == "unknown":
        outcome = "unresolved"
    elif valid and observed.participation == "dnp":
        outcome = "dnp_needs_rules"
    elif valid:
        actual = _positive_stat(observed.actual_stat, "actual_stat")
        line = _positive_stat(quote.line, "line")
        if actual == line:
            outcome = "push"
        elif actual > line:
            outcome = "selected_over" if quote.side == "over" else "selected_under_lost"
        else:
            outcome = "selected_under" if quote.side == "under" else "selected_over_lost"

    return PropOutcomeComparison(
        quote_id=quote.quote_id, event_id=game.event_id,
        athlete_id=quote.athlete_id, market=quote.market, compared_at=cutoff,
        structurally_valid=valid, comparison=outcome,
        recorded_stat=observed.actual_stat if valid else None,
        original_line=quote.line, selected_side=quote.side,
        reasons=tuple(reasons),
    )
