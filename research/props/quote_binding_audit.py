"""Research-only immutable-quote binding audit for frozen player-prop selections.

An original quote ID alone does not bind its player, market, side, line, price
or source. This audit compares each submitted postgame quote against an
explicit *claimed pregame* quote fingerprint and a deterministic digest of
the frozen binding record. All timestamps/URLs remain unverified claims.

No network, disk I/O, bookmaker settlement, Play authorization, or changes
to the existing frozen-batch grading semantics.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json

from .frozen_batch_audit import FrozenPropSelection
from .prop_board import Game, PropQuote, SourceStamp, SPORT_MARKETS, _digest, _id, _utc


_CANONICAL_VERSION = "courtside-prop-quote-binding-v1"


def _sha256_json(payload: dict[str, object]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def quote_content_sha256(quote: PropQuote) -> str:
    """Canonical fingerprint of the exact original quote and its source stamp.

    A deterministic checksum, NOT evidence the sportsbook actually offered
    the line or that its source URL/digest was independently authenticated.
    """
    if not isinstance(quote, PropQuote):
        raise TypeError("quote must be PropQuote")
    return _sha256_json({
        "schema": _CANONICAL_VERSION,
        "quote_id": quote.quote_id,
        "event_id": quote.event_id,
        "athlete_id": quote.athlete_id,
        "team_id": quote.team_id,
        "market": quote.market,
        "period": quote.period,
        "side": quote.side,
        "line": quote.line,
        "american_odds": quote.american_odds,
        "sportsbook": quote.sportsbook,
        "source": {
            "provider": quote.source.provider,
            "url": quote.source.url,
            "published_at": quote.source.published_at.isoformat(),
            "captured_at": quote.source.captured_at.isoformat(),
            "raw_sha256": quote.source.raw_sha256,
            "rights_status": quote.source.rights_status,
        },
    })


def binding_record_sha256(
    selection_id: str, quote_id: str, frozen_at: datetime,
    quote_sha256: str,
) -> str:
    """Digest of the canonical archive *payload* for an original binding.

    The archive source's raw_sha256 must equal this digest. A claimed digest
    and a claimed pregame timestamp are not independent external evidence.
    """
    _id(selection_id, "selection_id")
    _id(quote_id, "quote_id")
    _digest(quote_sha256, "quote_sha256")
    freeze = _utc(frozen_at, "frozen_at")
    return _sha256_json({
        "schema": _CANONICAL_VERSION,
        "selection_id": selection_id,
        "quote_id": quote_id,
        "frozen_at": freeze.isoformat(),
        "quote_sha256": quote_sha256.lower(),
    })


@dataclass(frozen=True)
class FrozenQuoteBinding:
    """An externally archived, claimed pregame binding to the original quote."""
    selection_id: str
    quote_id: str
    frozen_at: datetime
    quote_sha256: str
    archive_source: SourceStamp

    def __post_init__(self) -> None:
        _id(self.selection_id, "selection_id")
        _id(self.quote_id, "quote_id")
        _digest(self.quote_sha256, "quote_sha256")
        object.__setattr__(self, "frozen_at", _utc(self.frozen_at, "frozen_at"))
        if not isinstance(self.archive_source, SourceStamp):
            raise ValueError("archive_source must be SourceStamp")


@dataclass(frozen=True)
class QuoteBindingRow:
    selection_id: str
    quote_id: str
    status: str  # bound or invalid
    reasons: tuple[str, ...]
    original_quote_sha256: str | None
    # This audit does not authenticate any source or authorize betting.
    source_independently_verified: bool = False
    scoring_eligible: bool = False


@dataclass(frozen=True)
class QuoteBindingAudit:
    event_id: str
    reviewed_at: datetime
    declared_selection_count: int
    bound: int
    invalid: int
    missing_binding: int
    orphan_bindings: int
    rows: tuple[QuoteBindingRow, ...]
    reasons: tuple[str, ...]
    structurally_valid: bool
    source_independently_verified: bool = False
    manifest_completeness_verified: bool = False
    scoring_eligible: bool = False
    official_book_settlement_verified: bool = False


def audit_frozen_quote_bindings(
    game: Game,
    selections: tuple[FrozenPropSelection, ...],
    quotes: tuple[PropQuote, ...],
    bindings: tuple[FrozenQuoteBinding, ...],
    as_of: datetime,
) -> QuoteBindingAudit:
    """Account for every declared selection and reject mutated quote snapshots.

    A valid audit only proves internal consistency of the *supplied* original
    binding record, quote and timestamps. It cannot prove that the original
    frozen manifest was complete or that an archive was actually captured
    before tipoff.
    """
    if not isinstance(game, Game):
        raise TypeError("game must be Game")
    for label, values, typ in (
        ("selections", selections, FrozenPropSelection),
        ("quotes", quotes, PropQuote),
        ("bindings", bindings, FrozenQuoteBinding),
    ):
        if not isinstance(values, tuple) or any(not isinstance(v, typ) for v in values):
            raise TypeError(f"{label} must be tuple of {typ.__name__}")
    cutoff = _utc(as_of, "as_of")
    reasons: list[str] = []
    if not selections:
        reasons.append("selection_manifest_empty")
    if cutoff <= game.scheduled_start:
        reasons.append("audit_not_after_event_start")

    by_binding: dict[str, list[FrozenQuoteBinding]] = {}
    for binding in bindings:
        by_binding.setdefault(binding.selection_id, []).append(binding)
    by_quote: dict[str, list[PropQuote]] = {}
    for quote in quotes:
        by_quote.setdefault(quote.quote_id, []).append(quote)

    selection_ids = Counter(s.selection_id for s in selections)
    selection_quote_ids = Counter(s.quote_id for s in selections)
    original_ids = set(selection_ids)
    orphan_bindings = sum(len(v) for key, v in by_binding.items() if key not in original_ids)
    if orphan_bindings:
        reasons.append("orphan_binding_not_in_frozen_selection_manifest")
    rows: list[QuoteBindingRow] = []

    for selection in selections:
        faults: list[str] = []
        if selection_ids[selection.selection_id] != 1:
            faults.append("duplicate_frozen_selection_id")
        if selection_quote_ids[selection.quote_id] != 1:
            faults.append("duplicate_selected_quote_id")
        if selection.frozen_at >= game.scheduled_start:
            faults.append("selection_frozen_at_or_after_tip")
        if selection.frozen_at > cutoff:
            faults.append("selection_frozen_after_review_cutoff")
        if cutoff <= game.scheduled_start:
            faults.append("audit_not_after_event_start")

        candidate_bindings = by_binding.get(selection.selection_id, [])
        binding = candidate_bindings[0] if len(candidate_bindings) == 1 else None
        if not candidate_bindings:
            faults.append("original_quote_binding_missing")
        elif len(candidate_bindings) > 1:
            faults.append("duplicate_or_ambiguous_binding_for_selection")

        candidate_quotes = by_quote.get(selection.quote_id, [])
        quote = candidate_quotes[0] if len(candidate_quotes) == 1 else None
        if not candidate_quotes:
            faults.append("original_quote_missing")
        elif len(candidate_quotes) > 1:
            faults.append("duplicate_or_ambiguous_quote_id")

        actual_digest: str | None = None
        if quote is not None:
            actual_digest = quote_content_sha256(quote)
            if quote.event_id != game.event_id:
                faults.append("quote_event_mismatch")
            if quote.team_id not in {game.home_team_id, game.away_team_id}:
                faults.append("quote_team_not_in_event")
            if quote.market not in SPORT_MARKETS[game.sport]:
                faults.append("quote_market_not_supported_for_sport")
            if quote.source.captured_at >= game.scheduled_start:
                faults.append("quote_captured_at_or_after_tip")
            if quote.source.captured_at > selection.frozen_at:
                faults.append("quote_captured_after_selection_freeze")
            if quote.source.captured_at > cutoff:
                faults.append("quote_source_after_review_cutoff")

        if binding is not None:
            if binding.quote_id != selection.quote_id:
                faults.append("binding_quote_id_mismatch")
            if binding.frozen_at != selection.frozen_at:
                faults.append("binding_freeze_time_mismatch")
            if binding.archive_source.captured_at > selection.frozen_at:
                faults.append("binding_archive_captured_after_freeze")
            if binding.archive_source.captured_at >= game.scheduled_start:
                faults.append("binding_archive_captured_at_or_after_tip")
            if binding.archive_source.captured_at > cutoff:
                faults.append("binding_archive_after_review_cutoff")
            expected_archive_digest = binding_record_sha256(
                binding.selection_id, binding.quote_id, binding.frozen_at,
                binding.quote_sha256,
            )
            if binding.archive_source.raw_sha256.lower() != expected_archive_digest:
                faults.append("binding_archive_payload_digest_mismatch")
            if quote is not None:
                if binding.quote_sha256.lower() != actual_digest:
                    faults.append("original_quote_content_changed")
                if binding.archive_source.published_at < quote.source.captured_at:
                    faults.append("binding_archive_published_before_quote_capture")
                if binding.archive_source.captured_at < quote.source.captured_at:
                    faults.append("binding_archive_captured_before_quote_capture")

        rows.append(QuoteBindingRow(
            selection_id=selection.selection_id,
            quote_id=selection.quote_id,
            status="invalid" if faults else "bound",
            reasons=tuple(dict.fromkeys(faults)),
            original_quote_sha256=binding.quote_sha256 if binding is not None else None,
        ))

    invalid = sum(row.status == "invalid" for row in rows)
    bound = len(rows) - invalid
    missing = sum("original_quote_binding_missing" in row.reasons for row in rows)
    if invalid:
        reasons.append("invalid_or_missing_quote_bindings_present")
    return QuoteBindingAudit(
        event_id=game.event_id, reviewed_at=cutoff,
        declared_selection_count=len(selections), bound=bound,
        invalid=invalid, missing_binding=missing,
        orphan_bindings=orphan_bindings, rows=tuple(rows),
        reasons=tuple(reasons),
        structurally_valid=bool(selections) and invalid == 0 and orphan_bindings == 0 and
                           cutoff > game.scheduled_start,
    )
