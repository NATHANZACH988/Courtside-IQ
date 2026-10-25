"""Sport-independent, research-only, point-in-time evidence ledger.

This is not a betting model, sportsbook feed, settlement service, or API contract.
It deliberately performs no network or filesystem I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
import re
from urllib.parse import urlsplit


# First adapters are taxonomies, not assertions that data feeds are licensed.
SPORT_MARKETS: dict[str, frozenset[str]] = {
    "NBA": frozenset({"points", "rebounds", "assists", "threes", "minutes"}),
    "NFL": frozenset({"passing_yards", "rushing_yards", "receiving_yards", "receptions", "passing_tds"}),
    "MLB": frozenset({"hits", "total_bases", "strikeouts", "pitcher_strikeouts"}),
    "NHL": frozenset({"shots_on_goal", "goals", "assists", "saves"}),
    "SOCCER": frozenset({"shots", "shots_on_target", "goals", "assists"}),
}
RIGHTS = frozenset({"unverified", "licensed", "restricted"})
_ID = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]*:[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
_SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _id(value: str, field: str) -> None:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{field} must be a provider-qualified stable ID (provider:value)")


def _text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be empty")


@dataclass(frozen=True)
class Event:
    sport: str
    event_id: str
    scheduled_start: datetime
    home_team_id: str
    away_team_id: str

    def __post_init__(self) -> None:
        if self.sport not in SPORT_MARKETS:
            raise ValueError(f"unsupported sport: {self.sport}")
        _id(self.event_id, "event_id")
        if not self.event_id.startswith(self.sport.lower() + ":"):
            raise ValueError("event_id must be sport-qualified (e.g. nfl:espn-123)")
        _id(self.home_team_id, "home_team_id")
        _id(self.away_team_id, "away_team_id")
        if self.home_team_id == self.away_team_id:
            raise ValueError("opposing teams must have different IDs")
        object.__setattr__(self, "scheduled_start", _utc(self.scheduled_start, "scheduled_start"))


@dataclass(frozen=True)
class SourceProof:
    provider: str
    source_url: str
    published_at: datetime
    captured_at: datetime
    rights: str = "unverified"
    content_sha256: str | None = None

    def __post_init__(self) -> None:
        _text(self.provider, "provider")
        _text(self.source_url, "source_url")
        url = urlsplit(self.source_url)
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError("source_url must be an HTTPS URL without embedded credentials")
        if self.rights not in RIGHTS:
            raise ValueError("rights must be unverified, licensed, or restricted")
        if self.content_sha256 is not None and not _SHA256.fullmatch(self.content_sha256):
            raise ValueError("content_sha256 must be a 64-character hex digest")
        published = _utc(self.published_at, "published_at")
        captured = _utc(self.captured_at, "captured_at")
        if published > captured:
            raise ValueError("source cannot be captured before it was published")
        object.__setattr__(self, "published_at", published)
        object.__setattr__(self, "captured_at", captured)


@dataclass(frozen=True)
class Observation:
    observation_id: str
    event_id: str
    kind: str  # pregame or postgame; postgame is never returned to pregame replay
    metric: str
    value: str | int | float
    source: SourceProof
    athlete_id: str | None = None
    team_id: str | None = None

    def __post_init__(self) -> None:
        _id(self.observation_id, "observation_id")
        _id(self.event_id, "event_id")
        if self.kind not in {"pregame", "postgame"}:
            raise ValueError("kind must be pregame or postgame")
        _text(self.metric, "metric")
        if self.athlete_id is not None:
            _id(self.athlete_id, "athlete_id")
            if self.team_id is None:
                raise ValueError("athlete observations require a game-specific team_id")
        if self.team_id is not None:
            _id(self.team_id, "team_id")
        if type(self.value) not in {str, int, float} or (
            isinstance(self.value, float) and not isfinite(self.value)
        ):
            raise ValueError("observation value must be a finite number or string")
        if isinstance(self.value, str) and not self.value.strip():
            raise ValueError("observation value must not be empty")


@dataclass(frozen=True)
class MarketQuote:
    quote_id: str
    event_id: str
    athlete_id: str
    team_id: str
    market: str
    line: float
    american_odds: int
    sportsbook: str
    source: SourceProof

    def __post_init__(self) -> None:
        for field in ("quote_id", "event_id", "athlete_id", "team_id"):
            _id(getattr(self, field), field)
        _text(self.market, "market")
        _text(self.sportsbook, "sportsbook")
        if type(self.line) not in {int, float} or not isfinite(self.line) or self.line < 0:
            raise ValueError("line must be a finite, nonnegative number")
        if type(self.american_odds) is not int or -100 < self.american_odds < 100:
            raise ValueError("american_odds must be <= -100 or >= +100")


@dataclass(frozen=True)
class PregameSnapshot:
    event: Event
    as_of: datetime
    observations: tuple[Observation, ...]
    market_quotes: tuple[MarketQuote, ...]
    # Explicit hard gate: a provenance-safe snapshot is not a verified prediction.
    scoring_eligible: bool = False


class EvidenceLedger:
    """In-memory append-only research ledger. Duplicate IDs fail closed."""

    def __init__(self) -> None:
        self._events: dict[str, Event] = {}
        self._observations: dict[str, Observation] = {}
        self._quotes: dict[str, MarketQuote] = {}

    def add_event(self, event: Event) -> None:
        if event.event_id in self._events:
            raise ValueError("duplicate event_id")
        self._events[event.event_id] = event

    def _event_team(self, event_id: str, team_id: str | None) -> Event:
        if event_id not in self._events:
            raise ValueError("event is not registered")
        event = self._events[event_id]
        if team_id is not None and team_id not in {event.home_team_id, event.away_team_id}:
            raise ValueError("team_id is not part of the specified event")
        return event

    def add_observation(self, item: Observation) -> None:
        event = self._event_team(item.event_id, item.team_id)
        if item.observation_id in self._observations:
            raise ValueError("duplicate observation_id")
        if item.kind == "pregame" and item.source.captured_at >= event.scheduled_start:
            raise ValueError("pregame evidence captured at or after tipoff/kickoff")
        if item.kind == "postgame" and item.source.captured_at < event.scheduled_start:
            raise ValueError("postgame evidence cannot precede scheduled start")
        self._observations[item.observation_id] = item

    def add_market_quote(self, item: MarketQuote) -> None:
        event = self._event_team(item.event_id, item.team_id)
        if item.quote_id in self._quotes:
            raise ValueError("duplicate quote_id")
        if item.market not in SPORT_MARKETS[event.sport]:
            raise ValueError(f"market {item.market!r} not registered for {event.sport}")
        if item.source.captured_at >= event.scheduled_start:
            raise ValueError("pregame market quote captured at or after start")
        self._quotes[item.quote_id] = item

    def pregame_as_of(self, event_id: str, as_of: datetime) -> PregameSnapshot:
        event = self._event_team(event_id, None)
        cutoff = _utc(as_of, "as_of")
        if cutoff >= event.scheduled_start:
            raise ValueError("pregame cutoff must be strictly earlier than scheduled start")

        def visible(source: SourceProof) -> bool:
            # effective/event dates alone never prove data existed at the cutoff.
            return source.published_at <= cutoff and source.captured_at <= cutoff

        observations = tuple(sorted(
            (x for x in self._observations.values()
             if x.event_id == event_id and x.kind == "pregame" and visible(x.source)),
            key=lambda x: x.observation_id,
        ))
        quotes = tuple(sorted(
            (x for x in self._quotes.values() if x.event_id == event_id and visible(x.source)),
            key=lambda x: x.quote_id,
        ))
        return PregameSnapshot(event, cutoff, observations, quotes)
