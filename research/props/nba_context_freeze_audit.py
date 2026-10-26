"""Independent, research-only point-in-time NBA game-bank audit.

The parent context audit counts banked games at the board review cutoff.
This sibling gate additionally checks the *projection input cutoff* for
each considered player prop, preventing later games from retroactively
justifying a frozen forecast. It never modifies the source context audit,
projections, scoring rules, historical grades, or shared API contract.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from .nba_context_audit import (
    BankedGameEvidence, NBAPropContextAudit, OpponentDefenseEvidence,
    PlayerRoleEvidence, audit_nba_prop_context,
)
from .prop_board import (
    Game, PropProjection, PropQuote, PropScreen, RosterAthlete, _utc,
)


@dataclass(frozen=True)
class NBAFrozenBankRow:
    athlete_id: str
    team_id: str
    market: str
    decision: str
    projection_inputs_as_of: datetime | None
    home_bank_games_at_inputs: int | None
    away_bank_games_at_inputs: int | None
    five_game_bank_at_inputs: bool | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class NBAFrozenBankAudit:
    event_id: str
    checked_at: datetime
    parent_context_complete: bool
    projection_bank_complete: bool
    context_complete: bool
    expected_player_market_rows: int
    rows: tuple[NBAFrozenBankRow, ...]
    reasons: tuple[str, ...]
    source_independently_verified: bool = False
    scoring_authorized: bool = False
    play_authorized: bool = False


def audit_nba_frozen_bank(
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
) -> NBAFrozenBankAudit:
    """Audit five games for *each* team as known at each projection's input cutoff.

    Parent context validation is always run first. The returned rows
    preserve the full supplied roster × market denominator, including
    excluded/unresolved/unscreened player markets. All source timestamps
    and identities are unverified caller declarations, not official NBA
    attestations.
    """
    parent: NBAPropContextAudit = audit_nba_prop_context(
        game, roster, markets, screens, projections, quotes, banked_games,
        roles, defense, as_of, season=season,
    )
    cutoff = _utc(as_of, "as_of")
    screen_counts = Counter((s.athlete_id, s.market) for s in screens)
    screen_by_key = {(s.athlete_id, s.market): s for s in screens}
    projection_counts = Counter((p.athlete_id, p.market) for p in projections)
    projection_by_key = {(p.athlete_id, p.market): p for p in projections}
    roster_counts = Counter(p.athlete_id for p in roster)
    bank_counts = Counter((b.team_id, b.event_id) for b in banked_games)
    teams = (game.home_team_id, game.away_team_id)

    def bank_at_inputs(inputs_at: datetime) -> tuple[int, int]:
        # Exclude duplicates and invalid receipts rather than counting
        # any favorable subset or relying on the parent review cutoff.
        seen = {teams[0]: set(), teams[1]: set()}
        for bank in banked_games:
            if (bank.team_id not in seen or bank.season != season or
                    bank.event_id == game.event_id or
                    bank_counts[bank.team_id, bank.event_id] != 1 or
                    bank.game_final_at > inputs_at or
                    bank.game_final_at >= game.scheduled_start or
                    bank.source.published_at < bank.game_final_at or
                    bank.source.captured_at < bank.game_final_at or
                    bank.source.published_at > inputs_at or
                    bank.source.captured_at > inputs_at or
                    bank.source.captured_at >= game.scheduled_start):
                continue
            seen[bank.team_id].add(bank.event_id)
        return len(seen[teams[0]]), len(seen[teams[1]])

    rows: list[NBAFrozenBankRow] = []
    issues: list[str] = []
    for person in roster:
        for market in markets:
            key = (person.athlete_id, market)
            screen = screen_by_key.get(key)
            decision = screen.decision if screen is not None else "missing"
            faults: list[str] = []
            inputs: datetime | None = None
            home: int | None = None
            away: int | None = None
            met: bool | None = None
            if screen_counts[key] > 1:
                faults.append("ambiguous_player_market_screen")
            if roster_counts[person.athlete_id] > 1:
                faults.append("ambiguous_roster_identity")
            if decision == "consider":
                if projection_counts[key] != 1:
                    faults.append("missing_or_ambiguous_frozen_projection")
                else:
                    projection = projection_by_key[key]
                    inputs = projection.inputs_as_of
                    if projection.team_id != person.team_id:
                        faults.append("projection_team_identity_mismatch")
                    if inputs >= game.scheduled_start or inputs > cutoff:
                        faults.append("projection_inputs_not_pregame")
                    else:
                        home, away = bank_at_inputs(inputs)
                        met = home >= 5 and away >= 5
                        if not met:
                            faults.append("five_games_per_team_not_banked_at_projection_inputs")
            if faults:
                issues.append(f"{person.athlete_id}:{market}:" + ",".join(faults))
            rows.append(NBAFrozenBankRow(
                athlete_id=person.athlete_id, team_id=person.team_id,
                market=market, decision=decision, projection_inputs_as_of=inputs,
                home_bank_games_at_inputs=home, away_bank_games_at_inputs=away,
                five_game_bank_at_inputs=met, reasons=tuple(faults),
            ))

    complete = parent.context_complete and not issues
    return NBAFrozenBankAudit(
        event_id=game.event_id, checked_at=cutoff,
        parent_context_complete=parent.context_complete,
        projection_bank_complete=not issues,
        context_complete=complete,
        expected_player_market_rows=parent.expected_player_market_rows,
        rows=tuple(rows), reasons=tuple(parent.reasons) + tuple(issues),
    )
