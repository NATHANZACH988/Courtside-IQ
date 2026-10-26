"""Read-only NBA full-roster screening manifest integrity audit.

A player-prop projection cannot be called "full-roster screened" merely
because a later review supplies a complete-looking roster. Freeze the
*entire declared universe and every market decision* before the earliest
considered projection's input cutoff, and compare it to a supplied
content-addressed receipt.

This is internal consistency, NOT third-party proof that the manifest was
actually published, complete, or archived at the declared time.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json

from .prop_board import (
    Game, PropProjection, PropScreen, RosterAthlete, SourceStamp,
    SPORT_MARKETS, _utc,
)


_SCHEMA = "nba-full-roster-screen-v1"


@dataclass(frozen=True)
class ScreenManifestRow:
    athlete_id: str
    team_id: str
    market: str
    decision: str
    roster_source_known_at_manifest: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ScreenProjectionRow:
    athlete_id: str
    market: str
    projection_inputs_as_of: datetime
    manifest_known_at_inputs: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class FrozenScreenManifestAudit:
    event_id: str
    checked_at: datetime
    expected_player_market_rows: int
    supplied_screen_rows: int
    manifest_sha256: str
    manifest_hash_matches_receipt: bool
    full_declared_roster_screen: bool
    all_roster_sources_known_at_manifest: bool
    manifest_known_before_all_considered_inputs: bool
    structurally_valid: bool
    rows: tuple[ScreenManifestRow, ...]
    projection_rows: tuple[ScreenProjectionRow, ...]
    reasons: tuple[str, ...]
    # A matching hash cannot attest that the *original* universe was complete.
    external_archive_verified: bool = False
    independently_verified_roster_complete: bool = False
    production_scoring_authorized: bool = False
    play_authorized: bool = False


def _check_inputs(
    game: Game,
    roster: tuple[RosterAthlete, ...],
    markets: tuple[str, ...],
    screens: tuple[PropScreen, ...],
    projections: tuple[PropProjection, ...],
    receipt: SourceStamp,
) -> None:
    if not isinstance(game, Game) or game.sport != "NBA":
        raise ValueError("NBA game required")
    if not isinstance(roster, tuple) or any(
            not isinstance(x, RosterAthlete) for x in roster):
        raise TypeError("roster must contain RosterAthlete records")
    if (not isinstance(markets, tuple) or not markets or
            any(not isinstance(m, str) or m not in SPORT_MARKETS["NBA"]
                for m in markets) or len(set(markets)) != len(markets)):
        raise ValueError("markets must be unique supported NBA player-stat markets")
    if not isinstance(screens, tuple) or any(
            not isinstance(x, PropScreen) for x in screens):
        raise TypeError("screens must contain PropScreen records")
    if not isinstance(projections, tuple) or any(
            not isinstance(x, PropProjection) for x in projections):
        raise TypeError("projections must contain PropProjection records")
    if not isinstance(receipt, SourceStamp):
        raise TypeError("manifest receipt must be a SourceStamp")


def _source_payload(source: SourceStamp) -> dict[str, str]:
    return {
        "provider": source.provider,
        "url": source.url,
        "published_at": source.published_at.isoformat(),
        "captured_at": source.captured_at.isoformat(),
        "raw_sha256": source.raw_sha256.lower(),
        "rights_status": source.rights_status,
    }


def _manifest_payload(
    game: Game,
    roster: tuple[RosterAthlete, ...],
    markets: tuple[str, ...],
    screens: tuple[PropScreen, ...],
) -> dict[str, object]:
    return {
        "schema": _SCHEMA,
        "sport": game.sport,
        "event_id": game.event_id,
        "home_team_id": game.home_team_id,
        "away_team_id": game.away_team_id,
        "scheduled_start": game.scheduled_start.isoformat(),
        "markets": sorted(markets),
        "roster": sorted((
            {
                "athlete_id": x.athlete_id,
                "team_id": x.team_id,
                "availability": x.availability,
                "source": _source_payload(x.source),
            }
            for x in roster
        ), key=lambda x: (x["athlete_id"], x["team_id"], x["availability"])),
        "screens": sorted((
            {
                "athlete_id": x.athlete_id,
                "team_id": x.team_id,
                "market": x.market,
                "decision": x.decision,
                "reason": x.reason,
            }
            for x in screens
        ), key=lambda x: (x["athlete_id"], x["market"], x["team_id"],
                          x["decision"], x["reason"])),
    }


def nba_screen_manifest_sha256(
    game: Game,
    roster: tuple[RosterAthlete, ...],
    markets: tuple[str, ...],
    screens: tuple[PropScreen, ...],
) -> str:
    """Deterministic content hash; does not establish independent publication.

    Sorts the supplied rows to make ordering immaterial. The schema version
    and source receipt declarations are included. This hash must be stored
    in an independently archived receipt *before* prediction inputs freeze.
    """
    if not isinstance(game, Game) or game.sport != "NBA":
        raise ValueError("NBA game required")
    if not isinstance(roster, tuple) or any(
            not isinstance(x, RosterAthlete) for x in roster):
        raise TypeError("invalid roster")
    if not isinstance(markets, tuple) or any(
            not isinstance(m, str) for m in markets):
        raise TypeError("invalid markets")
    if not isinstance(screens, tuple) or any(
            not isinstance(x, PropScreen) for x in screens):
        raise TypeError("invalid screens")
    encoded = json.dumps(
        _manifest_payload(game, roster, markets, screens),
        sort_keys=True, ensure_ascii=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def audit_nba_frozen_screen_manifest(
    game: Game,
    roster: tuple[RosterAthlete, ...],
    markets: tuple[str, ...],
    screens: tuple[PropScreen, ...],
    projections: tuple[PropProjection, ...],
    receipt: SourceStamp,
    as_of: datetime,
) -> FrozenScreenManifestAudit:
    """Audit the supplied full-roster screen against a claimed frozen receipt.

    The full roster must be sourced by the manifest capture time; every
    considered player-market must have exactly one independent projection
    whose *inputs_as_of* is no earlier than the manifest receipt. An
    externally authenticated immutable archive is still required before
    claiming the original screening denominator is proven.
    """
    _check_inputs(game, roster, markets, screens, projections, receipt)
    cutoff = _utc(as_of, "as_of")
    if cutoff >= game.scheduled_start:
        raise ValueError("screen review cutoff must precede scheduled tipoff")

    faults: list[str] = []
    receipt_pregame = (receipt.captured_at <= cutoff and
                       receipt.captured_at < game.scheduled_start)
    if not receipt_pregame:
        faults.append("screen_manifest_receipt_not_known_pregame")
    digest = nba_screen_manifest_sha256(game, roster, markets, screens)
    matches = digest == receipt.raw_sha256.lower()
    if not matches:
        faults.append("screen_manifest_content_hash_mismatch")

    roster_counts = Counter(x.athlete_id for x in roster)
    roster_by_id = {x.athlete_id: x for x in roster}
    screen_counts = Counter((x.athlete_id, x.market) for x in screens)
    screen_by_key = {(x.athlete_id, x.market): x for x in screens}
    projection_counts = Counter((x.athlete_id, x.market) for x in projections)
    projection_by_key = {(x.athlete_id, x.market): x for x in projections}
    expected = {(x.athlete_id, market) for x in roster for market in markets}

    if not roster:
        faults.append("empty_roster_universe")
    if {x.team_id for x in roster} != {game.home_team_id, game.away_team_id}:
        faults.append("both_event_teams_required")
    for athlete_id, count in roster_counts.items():
        if count != 1:
            faults.append("duplicate_roster_identity:" + athlete_id)
    for key, count in screen_counts.items():
        if count != 1:
            faults.append("duplicate_player_market_screen:" + ":".join(key))
        if key not in expected:
            faults.append("orphan_player_market_screen:" + ":".join(key))
    for key, count in projection_counts.items():
        if count != 1:
            faults.append("duplicate_player_market_projection:" + ":".join(key))
        screen = screen_by_key.get(key)
        if key not in expected or screen is None or screen.decision != "consider":
            faults.append("projection_without_considered_screen:" + ":".join(key))

    rows: list[ScreenManifestRow] = []
    all_sources_known = True
    for person in roster:
        known = (person.source.published_at <= receipt.captured_at and
                 person.source.captured_at <= receipt.captured_at and
                 person.source.captured_at < game.scheduled_start)
        if not known:
            all_sources_known = False
            faults.append("roster_source_after_screen_manifest:" + person.athlete_id)
        for market in markets:
            key = (person.athlete_id, market)
            item = screen_by_key.get(key)
            row_faults: list[str] = []
            if screen_counts[key] != 1:
                row_faults.append("missing_or_ambiguous_player_market_screen")
            if roster_counts[person.athlete_id] != 1:
                row_faults.append("ambiguous_roster_identity")
            if item is not None and item.team_id != person.team_id:
                row_faults.append("screen_team_mismatch")
            if item is not None and item.decision == "consider" and person.availability != "active":
                row_faults.append("ineligible_or_uncertain_player_considered")
            if item is not None and item.decision == "exclude" and person.availability in {
                    "unknown", "questionable"}:
                row_faults.append("uncertain_player_must_remain_unresolved")
            if not known:
                row_faults.append("roster_source_not_known_at_screen_freeze")
            if row_faults:
                faults.extend(f"{person.athlete_id}:{market}:{x}" for x in row_faults)
            rows.append(ScreenManifestRow(
                person.athlete_id, person.team_id, market,
                item.decision if item is not None else "missing",
                known, tuple(row_faults),
            ))

    projection_rows: list[ScreenProjectionRow] = []
    projections_ready = True
    for key in sorted(expected):
        screen = screen_by_key.get(key)
        if screen is None or screen.decision != "consider":
            continue
        count = projection_counts[key]
        if count != 1:
            projections_ready = False
            faults.append("considered_player_projection_missing_or_ambiguous:" + ":".join(key))
            continue
        projection = projection_by_key[key]
        person = roster_by_id[key[0]]
        row_faults: list[str] = []
        if projection.team_id != person.team_id:
            row_faults.append("projection_team_mismatch")
        known_at_inputs = (receipt.captured_at <= projection.inputs_as_of and
                           receipt.published_at <= projection.inputs_as_of and
                           receipt.captured_at <= projection.frozen_at and
                           projection.frozen_at <= cutoff and
                           projection.frozen_at < game.scheduled_start)
        if not known_at_inputs:
            row_faults.append("screen_manifest_not_frozen_before_projection_inputs")
        if row_faults:
            projections_ready = False
            faults.extend(f"{key[0]}:{key[1]}:{x}" for x in row_faults)
        projection_rows.append(ScreenProjectionRow(
            key[0], key[1], projection.inputs_as_of, known_at_inputs,
            tuple(row_faults),
        ))

    complete = (not faults and len(screen_counts) == len(expected) and
                all_sources_known and projections_ready)
    return FrozenScreenManifestAudit(
        event_id=game.event_id, checked_at=cutoff,
        expected_player_market_rows=len(expected),
        supplied_screen_rows=len(screens),
        manifest_sha256=digest,
        manifest_hash_matches_receipt=matches,
        full_declared_roster_screen=(
            bool(expected) and len(screen_counts) == len(expected) and
            all(screen_counts[key] == 1 for key in expected) and
            all(key in expected for key in screen_counts) and
            all(count == 1 for count in roster_counts.values()) and
            {x.team_id for x in roster} == {game.home_team_id, game.away_team_id}
        ),
        all_roster_sources_known_at_manifest=all_sources_known,
        manifest_known_before_all_considered_inputs=projections_ready,
        structurally_valid=complete,
        rows=tuple(rows), projection_rows=tuple(projection_rows),
        reasons=tuple(dict.fromkeys(faults)),
    )
