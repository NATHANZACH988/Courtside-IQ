"""Research-only frozen NBA player-prop projection content binding.

The full-roster screening manifest is necessary but does not bind numeric
predictions. This audit binds each considered athlete/market's *exact*
prediction value and inputs/freeze timestamps to a separately supplied
archive receipt, and checks that it predates the market quote.

All timestamps, content digests, and archive identities are DECLARATIONS.
There is no network, filesystem I/O, scoring, or betting authorization.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json

from .nba_frozen_screen_manifest import (
    audit_nba_frozen_screen_manifest, nba_screen_manifest_sha256,
)
from .prop_board import (
    Game, PropProjection, PropQuote, PropScreen, RosterAthlete, SourceStamp,
    _digest, _id, _utc,
)

_SCHEMA = "nba-frozen-projection-binding-v1"


def _canonical_sha256(payload: dict[str, object]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True,
                             allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def nba_projection_content_sha256(game: Game, projection: PropProjection) -> str:
    """Fingerprint exact projection content, not a forecast-quality metric."""
    if not isinstance(game, Game) or game.sport != "NBA":
        raise ValueError("NBA game required")
    if not isinstance(projection, PropProjection):
        raise TypeError("projection must be PropProjection")
    return _canonical_sha256({
        "schema": _SCHEMA,
        "event_id": game.event_id,
        "scheduled_start": game.scheduled_start.isoformat(),
        "home_team_id": game.home_team_id,
        "away_team_id": game.away_team_id,
        "athlete_id": projection.athlete_id,
        "team_id": projection.team_id,
        "market": projection.market,
        "predicted_stat": projection.predicted_stat,
        "inputs_as_of": projection.inputs_as_of.isoformat(),
        "frozen_at": projection.frozen_at.isoformat(),
        "artifact_sha256": projection.artifact_sha256.lower(),
    })


def nba_projection_binding_record_sha256(
    game: Game, projection: PropProjection, screen_manifest_sha256: str,
    projection_sha256: str,
) -> str:
    """Fingerprint an archive payload binding prediction to its full roster."""
    _digest(screen_manifest_sha256, "screen_manifest_sha256")
    _digest(projection_sha256, "projection_sha256")
    if not isinstance(projection, PropProjection):
        raise TypeError("projection must be PropProjection")
    if not isinstance(game, Game) or game.sport != "NBA":
        raise ValueError("NBA game required")
    return _canonical_sha256({
        "schema": _SCHEMA,
        "event_id": game.event_id,
        "athlete_id": projection.athlete_id,
        "team_id": projection.team_id,
        "market": projection.market,
        "frozen_at": projection.frozen_at.isoformat(),
        "screen_manifest_sha256": screen_manifest_sha256.lower(),
        "projection_sha256": projection_sha256.lower(),
    })


@dataclass(frozen=True)
class FrozenNBAProjectionReceipt:
    """Caller-supplied alleged pregame archive receipt for one projection."""
    athlete_id: str
    team_id: str
    market: str
    screen_manifest_sha256: str
    projection_sha256: str
    archive_source: SourceStamp

    def __post_init__(self) -> None:
        _id(self.athlete_id, "athlete_id")
        _id(self.team_id, "team_id")
        if not isinstance(self.market, str) or not self.market.strip():
            raise ValueError("market required")
        _digest(self.screen_manifest_sha256, "screen_manifest_sha256")
        _digest(self.projection_sha256, "projection_sha256")
        if not isinstance(self.archive_source, SourceStamp):
            raise TypeError("archive_source must be SourceStamp")


@dataclass(frozen=True)
class NBAProjectionBindingRow:
    athlete_id: str
    team_id: str
    market: str
    status: str  # bound or invalid
    quote_count: int
    reasons: tuple[str, ...]
    external_archive_verified: bool = False
    play_authorized: bool = False


@dataclass(frozen=True)
class NBAProjectionBindingAudit:
    event_id: str
    checked_at: datetime
    considered_player_market_count: int
    supplied_receipt_count: int
    bound: int
    invalid: int
    missing_receipts: int
    full_roster_screen_valid: bool
    structurally_valid: bool
    rows: tuple[NBAProjectionBindingRow, ...]
    reasons: tuple[str, ...]
    # Hash agreement cannot establish independent provenance or calibration.
    external_archive_verified: bool = False
    independently_verified_original_predictions: bool = False
    prediction_accuracy_established: bool = False
    scoring_authorized: bool = False
    play_authorized: bool = False


def audit_nba_projection_bindings(
    game: Game,
    roster: tuple[RosterAthlete, ...],
    markets: tuple[str, ...],
    screens: tuple[PropScreen, ...],
    projections: tuple[PropProjection, ...],
    screen_receipt: SourceStamp,
    projection_receipts: tuple[FrozenNBAProjectionReceipt, ...],
    quotes: tuple[PropQuote, ...],
    as_of: datetime,
) -> NBAProjectionBindingAudit:
    """Verify every considered prediction is content-bound before its quote.

    A valid result is only internal consistency. An immutable, independent
    pregame archive is needed to establish that any receipt is genuine.
    """
    if (not isinstance(projection_receipts, tuple) or any(
            not isinstance(x, FrozenNBAProjectionReceipt) for x in projection_receipts)):
        raise TypeError("projection_receipts must contain FrozenNBAProjectionReceipt")
    if not isinstance(quotes, tuple) or any(not isinstance(x, PropQuote) for x in quotes):
        raise TypeError("quotes must contain PropQuote")
    parent = audit_nba_frozen_screen_manifest(
        game, roster, markets, screens, projections, screen_receipt, as_of,
    )
    cutoff = _utc(as_of, "as_of")
    screen_hash = nba_screen_manifest_sha256(game, roster, markets, screens)
    roster_by_id = {a.athlete_id: a for a in roster}
    considered = {(s.athlete_id, s.market) for s in screens if s.decision == "consider"}
    projection_counts = Counter((p.athlete_id, p.market) for p in projections)
    projection_by_key = {(p.athlete_id, p.market): p for p in projections}
    receipt_counts = Counter((r.athlete_id, r.market) for r in projection_receipts)
    receipt_by_key = {(r.athlete_id, r.market): r for r in projection_receipts}
    quotes_by_key: dict[tuple[str, str], list[PropQuote]] = {}
    issues: list[str] = list(parent.reasons)

    for quote in quotes:
        key = (quote.athlete_id, quote.market)
        if quote.event_id != game.event_id or quote.team_id not in {
                game.home_team_id, game.away_team_id}:
            issues.append("quote_wrong_event_or_team:" + quote.quote_id)
        if quote.source.captured_at > cutoff or quote.source.captured_at >= game.scheduled_start:
            issues.append("quote_not_known_pregame:" + quote.quote_id)
        if quote.source.published_at > cutoff:
            issues.append("quote_published_after_cutoff:" + quote.quote_id)
        quotes_by_key.setdefault(key, []).append(quote)

    for key, count in receipt_counts.items():
        if key not in considered:
            issues.append("orphan_projection_receipt:" + ":".join(key))
        if count > 1:
            issues.append("ambiguous_projection_receipts:" + ":".join(key))
    for key, count in projection_counts.items():
        if key not in considered:
            issues.append("projection_not_considered:" + ":".join(key))
        if count > 1:
            issues.append("ambiguous_projection_values:" + ":".join(key))

    rows: list[NBAProjectionBindingRow] = []
    for athlete_id, market in sorted(considered):
        key = (athlete_id, market)
        faults: list[str] = []
        person = roster_by_id.get(athlete_id)
        if person is None:
            faults.append("athlete_not_in_frozen_roster")
        if projection_counts[key] != 1:
            faults.append("missing_or_ambiguous_projection")
        if receipt_counts[key] != 1:
            faults.append("missing_or_ambiguous_projection_receipt")
        projection = projection_by_key.get(key) if projection_counts[key] == 1 else None
        binding = receipt_by_key.get(key) if receipt_counts[key] == 1 else None
        matching_quotes = quotes_by_key.get(key, [])
        if not matching_quotes:
            faults.append("original_posted_market_quote_missing")
        if projection is not None and person is not None and projection.team_id != person.team_id:
            faults.append("projection_team_mismatch")
        if binding is not None and person is not None and binding.team_id != person.team_id:
            faults.append("binding_team_mismatch")
        if binding is not None and binding.screen_manifest_sha256.lower() != screen_hash:
            faults.append("projection_not_bound_to_original_screen_manifest")
        if projection is not None and binding is not None:
            projection_hash = nba_projection_content_sha256(game, projection)
            if binding.projection_sha256.lower() != projection_hash:
                faults.append("frozen_projection_content_changed")
            expected_receipt_hash = nba_projection_binding_record_sha256(
                game, projection, binding.screen_manifest_sha256,
                binding.projection_sha256,
            )
            if binding.archive_source.raw_sha256.lower() != expected_receipt_hash:
                faults.append("projection_archive_payload_digest_mismatch")
            if binding.archive_source.published_at < projection.frozen_at:
                faults.append("projection_archive_published_before_freeze")
            if binding.archive_source.captured_at < projection.frozen_at:
                faults.append("projection_archive_captured_before_freeze")
            if binding.archive_source.captured_at < screen_receipt.captured_at:
                faults.append("projection_archive_before_roster_screen")
            if (binding.archive_source.captured_at > cutoff or
                    binding.archive_source.captured_at >= game.scheduled_start):
                faults.append("projection_archive_not_known_pregame")
            if binding.archive_source.published_at > cutoff:
                faults.append("projection_archive_published_after_cutoff")
            if projection.inputs_as_of < screen_receipt.captured_at:
                faults.append("projection_inputs_precede_roster_screen")
            if projection.frozen_at > cutoff or projection.frozen_at >= game.scheduled_start:
                faults.append("projection_frozen_after_review_or_tipoff")
            if projection.inputs_as_of > projection.frozen_at:
                faults.append("projection_inputs_after_freeze")
        for quote in matching_quotes:
            if person is None or quote.team_id != person.team_id:
                faults.append("quote_player_team_mismatch:" + quote.quote_id)
            if projection is not None and quote.source.captured_at < projection.frozen_at:
                faults.append("quote_before_projection_freeze:" + quote.quote_id)
            if binding is not None and quote.source.captured_at < binding.archive_source.captured_at:
                faults.append("quote_before_projection_archive:" + quote.quote_id)
        if faults:
            issues.extend(f"{athlete_id}:{market}:{reason}" for reason in faults)
        rows.append(NBAProjectionBindingRow(
            athlete_id=athlete_id,
            team_id=person.team_id if person is not None else "missing",
            market=market, status="invalid" if faults else "bound",
            quote_count=len(matching_quotes), reasons=tuple(dict.fromkeys(faults)),
        ))

    invalid = sum(row.status == "invalid" for row in rows)
    return NBAProjectionBindingAudit(
        event_id=game.event_id, checked_at=cutoff,
        considered_player_market_count=len(considered),
        supplied_receipt_count=len(projection_receipts),
        bound=len(rows) - invalid, invalid=invalid,
        missing_receipts=sum(receipt_counts[key] == 0 for key in considered),
        full_roster_screen_valid=parent.structurally_valid,
        structurally_valid=parent.structurally_valid and not issues and invalid == 0,
        rows=tuple(rows), reasons=tuple(dict.fromkeys(issues)),
    )
