"""NBA player-prop context evidence gates (research-only).

Screens the *entire* player/market universe before any candidate read.
Checks current-season game bank, injury/expected minutes, and opponent
defense as separate sourced inputs. Does not estimate a probability,
adjust a projection, certify sources, or authorize a betting Play.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import re

from .prop_board import (
    Game, PropProjection, PropQuote, PropScreen, RosterAthlete,
    SourceStamp, _id, _positive_stat, _utc, audit_prop_board,
)


_SEASON = re.compile(r"^(20[0-9]{2})-([0-9]{2})$")
_STATUSES = frozenset({"available", "probable", "questionable", "doubtful", "out", "unknown"})
_ROLES = frozenset({"starter", "rotation", "bench", "unknown"})


@dataclass(frozen=True)
class BankedGameEvidence:
    """One NBA current-season completed game for one team, with a receipt."""
    event_id: str
    team_id: str
    season: str
    game_final_at: datetime
    source: SourceStamp

    def __post_init__(self) -> None:
        _id(self.event_id, "event_id")
        _id(self.team_id, "team_id")
        if not self.event_id.startswith("nba:"):
            raise ValueError("banked event must be NBA")
        if not isinstance(self.season, str) or _SEASON.fullmatch(self.season) is None:
            raise ValueError("season must be YYYY-YY")
        if not isinstance(self.source, SourceStamp):
            raise ValueError("banked game needs a source receipt")
        object.__setattr__(self, "game_final_at", _utc(self.game_final_at, "game_final_at"))


@dataclass(frozen=True)
class PlayerRoleEvidence:
    """Official-injury *claim* plus separately sourced minutes/role assumption."""
    athlete_id: str
    team_id: str
    injury_status: str
    injury_source_kind: str  # official_report or unverified
    injury_source: SourceStamp
    expected_minutes: str | None
    role: str
    role_source: SourceStamp

    def __post_init__(self) -> None:
        _id(self.athlete_id, "athlete_id")
        _id(self.team_id, "team_id")
        if not isinstance(self.injury_status, str) or self.injury_status not in _STATUSES:
            raise ValueError("unsupported injury status")
        if self.injury_source_kind not in {"official_report", "unverified"}:
            raise ValueError("invalid injury source kind")
        if self.expected_minutes is not None:
            minutes = _positive_stat(self.expected_minutes, "expected_minutes")
            if minutes > 48:
                # Not a universal basketball minutes rule (overtime exists);
                # fail only at a generous validation bound.
                if minutes > 100:
                    raise ValueError("implausible expected minutes")
        if not isinstance(self.role, str) or self.role not in _ROLES:
            raise ValueError("unsupported role")
        if not isinstance(self.injury_source, SourceStamp) or not isinstance(
                self.role_source, SourceStamp):
            raise ValueError("injury and role sources are required")


@dataclass(frozen=True)
class OpponentDefenseEvidence:
    """Standalone opponent-defense observation, never a model adjustment."""
    opponent_team_id: str
    market: str
    period: str
    observed_games: int
    allowance_per_game: str
    methodology: str
    independent_of_player_projection: bool
    source: SourceStamp

    def __post_init__(self) -> None:
        _id(self.opponent_team_id, "opponent_team_id")
        if not isinstance(self.market, str) or not self.market.strip():
            raise ValueError("market is required")
        if self.period != "full_game":
            raise ValueError("defense period must be full_game")
        if type(self.observed_games) is not int or self.observed_games < 1:
            raise ValueError("defense observed_games must be positive")
        _positive_stat(self.allowance_per_game, "allowance_per_game")
        if not isinstance(self.methodology, str) or not self.methodology.strip():
            raise ValueError("defense methodology required")
        if type(self.independent_of_player_projection) is not bool:
            raise ValueError("independence declaration must be boolean")
        if not isinstance(self.source, SourceStamp):
            raise ValueError("defense source receipt required")


@dataclass(frozen=True)
class NBAPropContextRow:
    athlete_id: str
    team_id: str
    market: str
    decision: str  # consider, exclude, unresolved, missing
    opponent_team_id: str
    context_complete: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class NBAPropContextAudit:
    event_id: str
    season: str
    checked_at: datetime
    team_game_counts: tuple[tuple[str, int], ...]
    five_game_bank_met: bool
    expected_player_market_rows: int
    rows: tuple[NBAPropContextRow, ...]
    board_structurally_valid: bool
    context_complete: bool
    reasons: tuple[str, ...]
    # Source stamps and 'official_report' are user declarations, not
    # authenticated external provenance or rights.
    sources_independently_verified: bool = False
    probability_calibrated: bool = False
    scoring_authorized: bool = False
    play_authorized: bool = False


def audit_nba_prop_context(
    game: Game,
    roster: tuple[RosterAthlete, ...],
    markets: tuple[str, ...],
    screens: tuple[PropScreen, ...],
    projections: tuple[PropProjection, ...],
    quotes: tuple[PropQuote, ...],
    banked_games: tuple[BankedGameEvidence, ...],
    roles: tuple[PlayerRoleEvidence, ...],
    defense: tuple[OpponentDefenseEvidence, ...],
    as_of: datetime,
    *,
    season: str,
) -> NBAPropContextAudit:
    """Audit every roster player × market, not just shortlisted winners.

    The five-current-season-games-per-team floor is an owner research
    requirement, not a substitute for authenticated sources, pretip market
    rechecks, independent calibration, or production Play authorization.
    """
    if not isinstance(game, Game) or game.sport != "NBA":
        raise ValueError("NBA game required")
    if not isinstance(season, str):
        raise ValueError("season must be YYYY-YY")
    match = _SEASON.fullmatch(season)
    if match is None or int(match.group(2)) != (int(match.group(1)) + 1) % 100:
        raise ValueError("season must be a consecutive YYYY-YY season")
    for name, items, cls in (
        ("banked_games", banked_games, BankedGameEvidence),
        ("roles", roles, PlayerRoleEvidence),
        ("defense", defense, OpponentDefenseEvidence),
    ):
        if not isinstance(items, tuple) or any(not isinstance(x, cls) for x in items):
            raise TypeError(f"{name} must be a tuple of {cls.__name__}")
    cutoff = _utc(as_of, "as_of")
    board = audit_prop_board(game, roster, markets, screens, projections, quotes, cutoff)
    issues: list[str] = list(board.reasons)
    counts: dict[str, set[str]] = {
        game.home_team_id: set(), game.away_team_id: set(),
    }
    bank_keys = Counter((item.team_id, item.event_id) for item in banked_games)
    for item in banked_games:
        problems: list[str] = []
        if item.team_id not in counts:
            problems.append("bank_team_not_in_event")
        if item.event_id == game.event_id:
            problems.append("bank_includes_current_event")
        if item.season != season:
            problems.append("bank_wrong_season")
        if bank_keys[item.team_id, item.event_id] != 1:
            problems.append("bank_duplicate_event")
        if item.game_final_at >= game.scheduled_start or item.game_final_at > cutoff:
            problems.append("bank_game_not_completed_pregame")
        if (item.source.published_at < item.game_final_at or
                item.source.captured_at < item.game_final_at or
                item.source.published_at > cutoff or
                item.source.captured_at > cutoff):
            problems.append("bank_source_chronology_invalid")
        if problems:
            issues.extend(f"{problem}:{item.team_id}:{item.event_id}" for problem in problems)
        else:
            counts[item.team_id].add(item.event_id)
    bank_met = all(len(games) >= 5 for games in counts.values())
    if not bank_met:
        issues.append("five_current_season_games_per_team_not_banked")

    role_keys = Counter(item.athlete_id for item in roles)
    role_map = {item.athlete_id: item for item in roles}
    defense_keys = Counter((item.opponent_team_id, item.market) for item in defense)
    defense_map = {(item.opponent_team_id, item.market): item for item in defense}
    roster_map = {person.athlete_id: person for person in roster}
    screen_map = {(item.athlete_id, item.market): item for item in screens}
    projection_map = {(item.athlete_id, item.market): item for item in projections}
    for athlete_id in role_map:
        if athlete_id not in roster_map:
            issues.append("orphan_role_evidence:" + athlete_id)
    for key in defense_map:
        if key[0] not in counts or key[1] not in markets:
            issues.append("orphan_opponent_defense:" + ":".join(key))
    for athlete_id, count in role_keys.items():
        if count != 1:
            issues.append("duplicate_role_evidence:" + athlete_id)
    for key, count in defense_keys.items():
        if count != 1:
            issues.append("duplicate_opponent_defense:" + ":".join(key))

    def source_known(source: SourceStamp, frozen_at: datetime) -> bool:
        return (source.published_at <= frozen_at and
                source.captured_at <= frozen_at and
                source.captured_at < game.scheduled_start)

    rows: list[NBAPropContextRow] = []
    for person in roster:
        opponent = (game.away_team_id if person.team_id == game.home_team_id
                    else game.home_team_id)
        for market in markets:
            screen = screen_map.get((person.athlete_id, market))
            decision = screen.decision if screen is not None else "missing"
            faults: list[str] = []
            if screen is None:
                faults.append("missing_full_roster_market_screen")
            elif screen.team_id != person.team_id:
                faults.append("screen_team_mismatch")
            if decision == "consider":
                projection = projection_map.get((person.athlete_id, market))
                if projection is None:
                    faults.append("considered_projection_missing")
                if not bank_met:
                    faults.append("five_game_bank_not_met")
                if role_keys[person.athlete_id] != 1:
                    faults.append("missing_or_ambiguous_injury_role_evidence")
                else:
                    role = role_map[person.athlete_id]
                    if role.team_id != person.team_id:
                        faults.append("injury_role_wrong_team")
                    if role.injury_status != "available":
                        faults.append("injury_status_not_confirmed_available")
                    if role.injury_source_kind != "official_report":
                        faults.append("official_injury_report_not_claimed")
                    if role.role == "unknown":
                        faults.append("rotation_role_unresolved")
                    if role.expected_minutes is None or _positive_stat(
                            role.expected_minutes, "expected_minutes") == 0:
                        faults.append("expected_minutes_missing_or_zero")
                    if projection is not None and (
                            not source_known(role.injury_source, projection.inputs_as_of) or
                            not source_known(role.role_source, projection.inputs_as_of)):
                        faults.append("injury_or_minutes_updated_after_projection_inputs")
                dkey = (opponent, market)
                if defense_keys[dkey] != 1:
                    faults.append("missing_or_ambiguous_standalone_opponent_defense")
                else:
                    opponent_defense = defense_map[dkey]
                    if not opponent_defense.independent_of_player_projection:
                        faults.append("opponent_defense_not_independent")
                    if projection is not None and (
                            not source_known(opponent_defense.source, projection.inputs_as_of) or
                            opponent_defense.source.raw_sha256.lower() ==
                            projection.artifact_sha256.lower()):
                        faults.append("defense_not_independent_pregame_input")
            rows.append(NBAPropContextRow(
                athlete_id=person.athlete_id, team_id=person.team_id,
                market=market, decision=decision, opponent_team_id=opponent,
                context_complete=not faults and decision == "consider",
                reasons=tuple(dict.fromkeys(faults)),
            ))
    if any(row.reasons for row in rows):
        issues.append("incomplete_or_invalid_player_prop_context")
    return NBAPropContextAudit(
        event_id=game.event_id, season=season, checked_at=cutoff,
        team_game_counts=tuple(sorted((team, len(games)) for team, games in counts.items())),
        five_game_bank_met=bank_met,
        expected_player_market_rows=len(roster) * len(markets),
        rows=tuple(rows),
        board_structurally_valid=board.structurally_valid,
        context_complete=board.structurally_valid and bank_met and not issues,
        reasons=tuple(dict.fromkeys(issues)),
    )
