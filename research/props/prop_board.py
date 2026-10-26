"""Sport-neutral, research-only player-prop screening and price comparison.

No calls to sportsbooks, no settlement, no inferred probabilities, no betting
recommendations. All source/timestamp/digest fields are declarations.
The shared API contract and production scoring are entirely untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from urllib.parse import parse_qsl, urlsplit


SPORT_MARKETS: dict[str, frozenset[str]] = {
    "NBA": frozenset({"points", "rebounds", "assists", "threes", "blocks", "steals"}),
    "NFL": frozenset({"passing_yards", "rushing_yards", "receiving_yards",
                      "receptions", "passing_tds", "rushing_tds"}),
    "MLB": frozenset({"hits", "total_bases", "pitcher_strikeouts"}),
    "NHL": frozenset({"shots_on_goal", "saves", "goals", "assists"}),
    "SOCCER": frozenset({"shots", "shots_on_target", "goals", "assists"}),
}
_AVAILABILITY = frozenset({"active", "out", "questionable", "unknown"})
_DECISIONS = frozenset({"consider", "exclude", "unresolved"})
_RIGHTS = frozenset({"unverified", "restricted", "licensed"})
_ID = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]*:[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
_DIGEST = re.compile(r"^[a-fA-F0-9]{64}$")
_NUMBER = re.compile(r"^(0|[1-9][0-9]{0,6})(?:\.[0-9]{1,3})?$")
_SENSITIVE_QUERY = frozenset({"api_key", "apikey", "token", "access_token",
                               "secret", "password", "auth", "authorization",
                               "client_secret", "signature"})


def _id(value: object, label: str) -> None:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError(f"{label} must be a provider-qualified stable ID")


def _utc(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _digest(value: object, label: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{label} must be a SHA-256 digest")


def _positive_stat(value: object, label: str) -> Decimal:
    if not isinstance(value, str) or _NUMBER.fullmatch(value) is None:
        raise ValueError(f"{label} must be a nonnegative plain decimal string (<= 3 places)")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{label} is not a finite decimal") from exc
    if not number.is_finite():
        raise ValueError(f"{label} is not a finite decimal")
    return number


def _source_url(value: object) -> None:
    if not isinstance(value, str) or any(c.isspace() for c in value):
        raise ValueError("source_url must be credential-free HTTPS")
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or
                parsed.username is not None or parsed.password is not None or
                parsed.fragment):
            raise ValueError("source_url must be credential-free HTTPS")
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
            if key.casefold() in _SENSITIVE_QUERY:
                raise ValueError("source_url cannot expose query credentials")
    except ValueError as exc:
        raise ValueError("source_url must be credential-free HTTPS") from exc


@dataclass(frozen=True)
class Game:
    sport: str
    event_id: str
    home_team_id: str
    away_team_id: str
    scheduled_start: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.sport, str) or self.sport not in SPORT_MARKETS:
            raise ValueError("unsupported sport")
        _id(self.event_id, "event_id")
        if not self.event_id.startswith(self.sport.lower() + ":"):
            raise ValueError("event_id must have sport-specific namespace")
        _id(self.home_team_id, "home_team_id")
        _id(self.away_team_id, "away_team_id")
        if self.home_team_id == self.away_team_id:
            raise ValueError("opposing teams cannot be identical")
        object.__setattr__(self, "scheduled_start",
                           _utc(self.scheduled_start, "scheduled_start"))


@dataclass(frozen=True)
class SourceStamp:
    provider: str
    url: str
    published_at: datetime
    captured_at: datetime
    raw_sha256: str
    rights_status: str = "unverified"

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("provider is required")
        _source_url(self.url)
        _digest(self.raw_sha256, "raw_sha256")
        if not isinstance(self.rights_status, str) or self.rights_status not in _RIGHTS:
            raise ValueError("invalid rights_status")
        published = _utc(self.published_at, "published_at")
        captured = _utc(self.captured_at, "captured_at")
        if published > captured:
            raise ValueError("source captured before publication")
        object.__setattr__(self, "published_at", published)
        object.__setattr__(self, "captured_at", captured)


@dataclass(frozen=True)
class RosterAthlete:
    athlete_id: str
    team_id: str
    availability: str
    source: SourceStamp

    def __post_init__(self) -> None:
        _id(self.athlete_id, "athlete_id")
        _id(self.team_id, "team_id")
        if not isinstance(self.availability, str) or self.availability not in _AVAILABILITY:
            raise ValueError("invalid availability")
        if not isinstance(self.source, SourceStamp):
            raise ValueError("roster source must be a SourceStamp")


@dataclass(frozen=True)
class PropScreen:
    athlete_id: str
    team_id: str
    market: str
    decision: str
    reason: str

    def __post_init__(self) -> None:
        _id(self.athlete_id, "athlete_id")
        _id(self.team_id, "team_id")
        if not isinstance(self.market, str) or not self.market.strip():
            raise ValueError("market is required")
        if not isinstance(self.decision, str) or self.decision not in _DECISIONS:
            raise ValueError("decision must be consider, exclude, or unresolved")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("screen reason is mandatory")


@dataclass(frozen=True)
class PropProjection:
    athlete_id: str
    team_id: str
    market: str
    predicted_stat: str
    frozen_at: datetime
    inputs_as_of: datetime
    artifact_sha256: str

    def __post_init__(self) -> None:
        _id(self.athlete_id, "athlete_id")
        _id(self.team_id, "team_id")
        _positive_stat(self.predicted_stat, "predicted_stat")
        _digest(self.artifact_sha256, "artifact_sha256")
        if not isinstance(self.market, str) or not self.market.strip():
            raise ValueError("market is required")
        freeze = _utc(self.frozen_at, "frozen_at")
        input_time = _utc(self.inputs_as_of, "inputs_as_of")
        if input_time > freeze:
            raise ValueError("projection cannot use future inputs")
        object.__setattr__(self, "frozen_at", freeze)
        object.__setattr__(self, "inputs_as_of", input_time)


@dataclass(frozen=True)
class PropQuote:
    quote_id: str
    event_id: str
    athlete_id: str
    team_id: str
    market: str
    period: str
    side: str
    line: str
    american_odds: int
    sportsbook: str
    source: SourceStamp

    def __post_init__(self) -> None:
        for field in ("quote_id", "event_id", "athlete_id", "team_id"):
            _id(getattr(self, field), field)
        _positive_stat(self.line, "line")
        if not isinstance(self.market, str) or not self.market.strip():
            raise ValueError("market is required")
        if self.period != "full_game":
            raise ValueError("only explicit full_game markets are supported")
        if not isinstance(self.side, str) or self.side not in {"over", "under"}:
            raise ValueError("side must be over or under")
        if type(self.american_odds) is not int or -100 < self.american_odds < 100:
            raise ValueError("invalid American odds")
        if not isinstance(self.sportsbook, str) or not self.sportsbook.strip():
            raise ValueError("sportsbook required")
        if not isinstance(self.source, SourceStamp):
            raise ValueError("quote source must be a SourceStamp")


@dataclass(frozen=True)
class PropComparison:
    quote_id: str
    athlete_id: str
    market: str
    period: str
    side: str
    sportsbook: str
    line: str
    american_odds: int
    independent_projection: str
    model_minus_line: str
    # This is a stat-unit *difference*, NOT a probability, ROI or edge.
    probability_estimated: bool = False
    play_authorized: bool = False


@dataclass(frozen=True)
class BoardAudit:
    sport: str
    event_id: str
    as_of: datetime
    roster_athletes: int
    expected_screen_rows: int
    screened_rows: int
    considered: int
    excluded: int
    unresolved: int
    complete_roster_screen: bool
    structurally_valid: bool
    compared_quotes: tuple[PropComparison, ...]
    missing_quote_candidates: tuple[str, ...]
    reasons: tuple[str, ...]
    source_independently_verified: bool = False
    licensed_for_commercial_use: bool = False
    eligible_for_play: bool = False
    eligible_for_scoring: bool = False


def audit_prop_board(
    game: Game,
    roster: tuple[RosterAthlete, ...],
    markets: tuple[str, ...],
    screens: tuple[PropScreen, ...],
    projections: tuple[PropProjection, ...],
    quotes: tuple[PropQuote, ...],
    as_of: datetime,
) -> BoardAudit:
    """Validate *all-player/all-market* coverage before any quote comparisons.

    A structurally valid board can have no candidates or no market quotes.
    Neither it nor any included quote authorizes a Play classification. A
    missing quote remains explicit; the independent projection is never
    constructed or updated from a sportsbook line.
    """
    if not isinstance(game, Game):
        raise TypeError("game must be a Game")
    cutoff = _utc(as_of, "as_of")
    if cutoff >= game.scheduled_start:
        raise ValueError("pregame as_of must precede scheduled start")
    reasons: list[str] = []
    if (not isinstance(markets, tuple) or not markets or
            any(not isinstance(m, str) or m not in SPORT_MARKETS[game.sport] for m in markets) or
            len(set(markets)) != len(markets)):
        raise ValueError("markets must be unique supported player stat markets")

    def visible(source: SourceStamp, label: str) -> bool:
        if (source.published_at > cutoff or source.captured_at > cutoff or
                source.captured_at >= game.scheduled_start):
            reasons.append(label + "_source_not_known_pregame")
            return False
        return True

    by_athlete: dict[str, RosterAthlete] = {}
    covered_teams: set[str] = set()
    for person in roster:
        if not isinstance(person, RosterAthlete):
            raise TypeError("roster contains non-athlete")
        if person.team_id not in {game.home_team_id, game.away_team_id}:
            reasons.append("roster_team_not_in_event:" + person.athlete_id)
        else:
            covered_teams.add(person.team_id)
        if person.athlete_id in by_athlete:
            reasons.append("duplicate_roster_athlete:" + person.athlete_id)
        else:
            by_athlete[person.athlete_id] = person
        visible(person.source, "roster:" + person.athlete_id)
    if covered_teams != {game.home_team_id, game.away_team_id}:
        reasons.append("both_teams_roster_required")

    expected = {(a, m) for a in by_athlete for m in markets}
    by_screen: dict[tuple[str, str], PropScreen] = {}
    tallies = {"consider": 0, "exclude": 0, "unresolved": 0}
    for item in screens:
        if not isinstance(item, PropScreen):
            raise TypeError("screens contain non-PropScreen")
        key = (item.athlete_id, item.market)
        if key in by_screen:
            reasons.append("duplicate_player_market_screen:" + item.athlete_id + ":" + item.market)
            continue
        by_screen[key] = item
        if key not in expected:
            reasons.append("unexpected_player_market_screen:" + item.athlete_id + ":" + item.market)
            continue
        tallies[item.decision] += 1
        athlete = by_athlete[item.athlete_id]
        if item.team_id != athlete.team_id:
            reasons.append("screen_team_mismatch:" + item.athlete_id)
        if item.decision == "consider" and athlete.availability != "active":
            reasons.append("ineligible_or_uncertain_considered:" + item.athlete_id)
        if item.decision == "exclude" and athlete.availability in {"unknown", "questionable"}:
            # An uncertain roster status must remain explicitly unresolved.
            reasons.append("uncertain_availability_not_unresolved:" + item.athlete_id)
    missing = expected - set(by_screen)
    if missing:
        reasons.append("full_roster_market_screen_incomplete")

    considered_keys = {k for k, item in by_screen.items() if
                       item.decision == "consider" and k in expected}
    by_projection: dict[tuple[str, str], PropProjection] = {}
    for item in projections:
        if not isinstance(item, PropProjection):
            raise TypeError("projections contain non-PropProjection")
        key = (item.athlete_id, item.market)
        if key in by_projection:
            reasons.append("duplicate_projection:" + item.athlete_id + ":" + item.market)
            continue
        by_projection[key] = item
        if key not in considered_keys:
            reasons.append("projection_not_screened_consider:" + item.athlete_id)
            continue
        athlete = by_athlete[item.athlete_id]
        if item.team_id != athlete.team_id:
            reasons.append("projection_team_mismatch:" + item.athlete_id)
        if item.frozen_at > cutoff or item.frozen_at >= game.scheduled_start:
            reasons.append("projection_not_frozen_pregame:" + item.athlete_id)
    if considered_keys - set(by_projection):
        reasons.append("considered_player_projection_missing")

    comparisons: list[PropComparison] = []
    quoted: set[tuple[str, str]] = set()
    quote_keys: set[tuple[str, str, str, str, str]] = set()
    quote_ids: set[str] = set()
    for quote in quotes:
        if not isinstance(quote, PropQuote):
            raise TypeError("quotes contain non-PropQuote")
        if quote.quote_id in quote_ids:
            reasons.append("duplicate_quote_id:" + quote.quote_id)
            continue
        quote_ids.add(quote.quote_id)
        pair = (quote.athlete_id, quote.market)
        qkey = (quote.athlete_id, quote.market, quote.period, quote.side,
                quote.sportsbook.casefold())
        if qkey in quote_keys:
            reasons.append("duplicate_book_side_market_quote:" + quote.quote_id)
            continue
        quote_keys.add(qkey)
        if quote.event_id != game.event_id or quote.market not in markets:
            reasons.append("quote_event_or_market_mismatch:" + quote.quote_id)
            continue
        athlete = by_athlete.get(quote.athlete_id)
        if athlete is None or quote.team_id != athlete.team_id:
            reasons.append("quote_player_team_mismatch:" + quote.quote_id)
            continue
        if not visible(quote.source, "quote:" + quote.quote_id):
            continue
        if pair not in considered_keys:
            # Quote for an excluded player may be preserved but cannot create a pick.
            continue
        projection = by_projection.get(pair)
        if projection is None or projection.team_id != quote.team_id:
            continue
        if projection.frozen_at > quote.source.captured_at:
            reasons.append("market_quoted_before_independent_projection:" + quote.quote_id)
            continue
        quoted.add(pair)
        delta = _positive_stat(projection.predicted_stat, "predicted_stat") - _positive_stat(
            quote.line, "line")
        comparisons.append(PropComparison(
            quote.quote_id, quote.athlete_id, quote.market, quote.period,
            quote.side, quote.sportsbook, quote.line, quote.american_odds,
            projection.predicted_stat, str(delta),
        ))
    missing_quotes = tuple(sorted(
        f"{aid}:{market}" for aid, market in considered_keys - quoted
    ))
    # Readiness is intentionally distinct from structural source correctness.
    # Missing quotes do not invalidate an independent projection, but they
    # do prevent comparison and any real-market claim.
    return BoardAudit(
        sport=game.sport, event_id=game.event_id, as_of=cutoff,
        roster_athletes=len(by_athlete), expected_screen_rows=len(expected),
        screened_rows=len(expected - missing),
        considered=tallies["consider"], excluded=tallies["exclude"],
        unresolved=tallies["unresolved"],
        complete_roster_screen=not missing and bool(by_athlete) and
                             covered_teams == {game.home_team_id, game.away_team_id},
        structurally_valid=not reasons,
        compared_quotes=tuple(sorted(comparisons, key=lambda c: c.quote_id)),
        missing_quote_candidates=missing_quotes,
        reasons=tuple(reasons),
    )
