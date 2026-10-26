"""Read-only, pretip player-prop quote freshness and market-revision audit.

Does not fetch a sportsbook, assert data licensing, calculate probability,
revise the original frozen line, settle a bet, or authorize a Play.
SourceStamp timestamps and SHA-256 values remain unverified declarations.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from .frozen_batch_audit import FrozenPropSelection
from .prop_board import Game, PropQuote, SourceStamp, SPORT_MARKETS, _id, _positive_stat, _utc
from .quote_binding_audit import (
    FrozenQuoteBinding, binding_record_sha256, quote_content_sha256,
)


@dataclass(frozen=True)
class PretipMarketRecheck:
    """A newly observed status of the *same original book/player/market/side*.

    An open quote must supply a line and American price. Closed/unknown
    markets must not fabricate prices. This is a source *claim*, not proof
    the sportsbook accepted wagers or had a live market.
    """
    quote_id: str
    event_id: str
    athlete_id: str
    team_id: str
    market: str
    period: str
    side: str
    sportsbook: str
    status: Literal["open", "suspended", "withdrawn", "unknown"]
    line: str | None
    american_odds: int | None
    source: SourceStamp

    def __post_init__(self) -> None:
        for label in ("quote_id", "event_id", "athlete_id", "team_id"):
            _id(getattr(self, label), label)
        if not isinstance(self.market, str) or not self.market.strip():
            raise ValueError("market required")
        if (self.period != "full_game" or not isinstance(self.side, str) or
                self.side not in {"over", "under"}):
            raise ValueError("explicit full_game and over/under required")
        if not isinstance(self.sportsbook, str) or not self.sportsbook.strip():
            raise ValueError("sportsbook required")
        if (not isinstance(self.status, str) or
                self.status not in {"open", "suspended", "withdrawn", "unknown"}):
            raise ValueError("unsupported recheck status")
        if not isinstance(self.source, SourceStamp):
            raise ValueError("source must be SourceStamp")
        if self.status == "open":
            _positive_stat(self.line, "line")
            if (type(self.american_odds) is not int or
                    -100 < self.american_odds < 100):
                raise ValueError("open quote requires valid American odds")
        elif self.line is not None or self.american_odds is not None:
            raise ValueError("non-open recheck cannot claim a live line or price")


@dataclass(frozen=True)
class PretipRecheckRow:
    selection_id: str
    quote_id: str
    status: str  # unchanged/moved/suspended/withdrawn/unknown/stale/missing/invalid
    original_line: str | None
    original_american_odds: int | None
    latest_line: str | None
    latest_american_odds: int | None
    latest_capture: datetime | None
    reasons: tuple[str, ...]
    # Even an unchanged book quote is NOT a verified offer or Play.
    source_independently_verified: bool = False
    play_authorized: bool = False


@dataclass(frozen=True)
class PretipRecheckAudit:
    event_id: str
    checked_at: datetime
    declared_selection_count: int
    rows: tuple[PretipRecheckRow, ...]
    status_counts: tuple[tuple[str, int], ...]
    reasons: tuple[str, ...]
    structurally_valid: bool
    all_original_lines_still_observed: bool
    source_independently_verified: bool = False
    play_authorized: bool = False
    licensed_for_commercial_use: bool = False


def audit_pretip_market_rechecks(
    game: Game,
    selections: tuple[FrozenPropSelection, ...],
    original_quotes: tuple[PropQuote, ...],
    bindings: tuple[FrozenQuoteBinding, ...],
    rechecks: tuple[PretipMarketRecheck, ...],
    as_of: datetime,
    *,
    max_recheck_age_minutes: int,
    pretip_window_minutes: int,
) -> PretipRecheckAudit:
    """Reconcile *every* original selection against its latest pretip recheck.

    Freshness and pretip window thresholds must be supplied explicitly by
    the caller. Latest is chosen by *capture time*, never by favorable line,
    price or outcome. Conflicting same-time observations fail closed.
    """
    if not isinstance(game, Game):
        raise TypeError("game must be Game")
    for label, records, kind in (
        ("selections", selections, FrozenPropSelection),
        ("original_quotes", original_quotes, PropQuote),
        ("bindings", bindings, FrozenQuoteBinding),
        ("rechecks", rechecks, PretipMarketRecheck),
    ):
        if not isinstance(records, tuple) or any(not isinstance(x, kind) for x in records):
            raise TypeError(f"{label} must be a tuple of {kind.__name__}")
    for label, threshold in (
        ("max_recheck_age_minutes", max_recheck_age_minutes),
        ("pretip_window_minutes", pretip_window_minutes),
    ):
        if type(threshold) is not int or not 1 <= threshold <= 240:
            raise ValueError(f"{label} must be an explicit integer in 1..240")
    cutoff = _utc(as_of, "as_of")
    reasons: list[str] = []
    if not selections:
        reasons.append("frozen_selection_manifest_empty")
    if not (game.scheduled_start - timedelta(minutes=pretip_window_minutes)
            <= cutoff < game.scheduled_start):
        reasons.append("review_cutoff_outside_explicit_pretip_window")

    selection_counts = Counter(s.selection_id for s in selections)
    selected_quote_counts = Counter(s.quote_id for s in selections)
    quotes_by_id: dict[str, list[PropQuote]] = {}
    bindings_by_selection: dict[str, list[FrozenQuoteBinding]] = {}
    rechecks_by_quote: dict[str, list[PretipMarketRecheck]] = {}
    for q in original_quotes:
        quotes_by_id.setdefault(q.quote_id, []).append(q)
    for b in bindings:
        bindings_by_selection.setdefault(b.selection_id, []).append(b)
    for r in rechecks:
        rechecks_by_quote.setdefault(r.quote_id, []).append(r)

    if any(key not in selection_counts for key in bindings_by_selection):
        reasons.append("orphan_original_binding")
    if any(key not in selected_quote_counts for key in rechecks_by_quote):
        reasons.append("orphan_pretip_recheck")

    rows: list[PretipRecheckRow] = []
    for selection in selections:
        faults: list[str] = []
        if selection_counts[selection.selection_id] != 1:
            faults.append("duplicate_selection_id")
        if selected_quote_counts[selection.quote_id] != 1:
            faults.append("reused_original_quote_id")
        if selection.frozen_at >= game.scheduled_start or selection.frozen_at > cutoff:
            faults.append("selection_not_frozen_by_pretip_cutoff")
        if not (game.scheduled_start - timedelta(minutes=pretip_window_minutes)
                <= cutoff < game.scheduled_start):
            faults.append("review_cutoff_outside_explicit_pretip_window")

        quote_candidates = quotes_by_id.get(selection.quote_id, ())
        quote = quote_candidates[0] if len(quote_candidates) == 1 else None
        if quote is None:
            faults.append("missing_or_ambiguous_original_quote")
        binding_candidates = bindings_by_selection.get(selection.selection_id, ())
        binding = binding_candidates[0] if len(binding_candidates) == 1 else None
        if binding is None:
            faults.append("missing_or_ambiguous_frozen_quote_binding")
        if quote is not None:
            if quote.event_id != game.event_id or quote.team_id not in (
                    game.home_team_id, game.away_team_id):
                faults.append("original_quote_wrong_event_or_team")
            if quote.market not in SPORT_MARKETS[game.sport]:
                faults.append("original_market_not_supported_for_sport")
            if (quote.source.captured_at > selection.frozen_at or
                    quote.source.captured_at >= game.scheduled_start):
                faults.append("original_quote_not_captured_before_freeze")
        if binding is not None:
            if (binding.quote_id != selection.quote_id or
                    binding.frozen_at != selection.frozen_at):
                faults.append("binding_identity_or_freeze_mismatch")
            if (binding.archive_source.captured_at > selection.frozen_at or
                    binding.archive_source.captured_at >= game.scheduled_start):
                faults.append("binding_not_archived_by_selection_freeze")
            if binding.archive_source.raw_sha256.lower() != binding_record_sha256(
                    binding.selection_id, binding.quote_id, binding.frozen_at,
                    binding.quote_sha256):
                faults.append("binding_archive_digest_mismatch")
            if quote is not None:
                if quote_content_sha256(quote) != binding.quote_sha256.lower():
                    faults.append("original_quote_content_mismatch")
                if binding.archive_source.captured_at < quote.source.captured_at:
                    faults.append("binding_archive_before_original_quote")
                if binding.archive_source.published_at < quote.source.captured_at:
                    faults.append("binding_published_before_original_quote")

        candidates = rechecks_by_quote.get(selection.quote_id, ())
        # Validate the entire declared observation lineage. A later valid
        # record must not conceal an earlier wrong-player or post-freeze
        # cross-market record supplied under the same original quote ID.
        for historical in candidates:
            if historical.source.captured_at <= selection.frozen_at:
                faults.append("recheck_lineage_contains_prefreeze_capture")
            if historical.source.published_at < selection.frozen_at:
                faults.append("recheck_lineage_contains_prefreeze_publication")
            if quote is not None and (
                    historical.event_id != quote.event_id or
                    historical.athlete_id != quote.athlete_id or
                    historical.team_id != quote.team_id or
                    historical.market != quote.market or
                    historical.period != quote.period or
                    historical.side != quote.side or
                    historical.sportsbook.casefold() != quote.sportsbook.casefold()):
                faults.append("recheck_lineage_contains_identity_mismatch")
        latest: PretipMarketRecheck | None = None
        if not candidates:
            faults.append("missing_pretip_recheck")
        else:
            # A caller cannot make a more favorable earlier recheck win by
            # permuting the input; the latest capture always governs.
            newest_time = max(r.source.captured_at for r in candidates)
            newest = [r for r in candidates if r.source.captured_at == newest_time]
            if len(newest) != 1:
                faults.append("ambiguous_latest_recheck_same_capture_time")
            else:
                latest = newest[0]
            if any(r.source.captured_at > cutoff or
                   r.source.captured_at >= game.scheduled_start
                   for r in candidates):
                faults.append("future_or_posttip_recheck_supplied")
        if latest is not None:
            if latest.source.captured_at <= selection.frozen_at:
                faults.append("recheck_not_after_selection_freeze")
            if latest.source.published_at < selection.frozen_at:
                faults.append("recheck_publication_predates_selection")
            if latest.source.captured_at > cutoff:
                faults.append("recheck_not_available_by_cutoff")
            if cutoff - latest.source.captured_at > timedelta(
                    minutes=max_recheck_age_minutes):
                faults.append("recheck_stale_at_cutoff")
            if quote is not None:
                if (latest.event_id != quote.event_id or
                        latest.athlete_id != quote.athlete_id or
                        latest.team_id != quote.team_id or
                        latest.market != quote.market or
                        latest.period != quote.period or
                        latest.side != quote.side or
                        latest.sportsbook.casefold() != quote.sportsbook.casefold()):
                    faults.append("recheck_original_market_identity_mismatch")

        status = "invalid" if faults else "missing"
        if not faults and latest is not None and quote is not None:
            if latest.status == "open":
                status = ("unchanged" if latest.line == quote.line and
                          latest.american_odds == quote.american_odds else "moved")
            else:
                status = latest.status
        elif faults == ["missing_pretip_recheck"]:
            status = "missing"
        elif "recheck_stale_at_cutoff" in faults and len(faults) == 1:
            status = "stale"
        rows.append(PretipRecheckRow(
            selection_id=selection.selection_id, quote_id=selection.quote_id,
            status=status,
            original_line=quote.line if quote is not None else None,
            original_american_odds=quote.american_odds if quote is not None else None,
            latest_line=latest.line if latest is not None else None,
            latest_american_odds=latest.american_odds if latest is not None else None,
            latest_capture=latest.source.captured_at if latest is not None else None,
            reasons=tuple(dict.fromkeys(faults)),
        ))
    counts = Counter(row.status for row in rows)
    if any(row.reasons for row in rows):
        reasons.append("incomplete_or_invalid_pretip_market_evidence")
    if any(row.status in {"moved", "suspended", "withdrawn", "unknown"}
           for row in rows):
        reasons.append("market_changed_or_unavailable_since_original_freeze")
    return PretipRecheckAudit(
        event_id=game.event_id, checked_at=cutoff,
        declared_selection_count=len(selections), rows=tuple(rows),
        status_counts=tuple(sorted(counts.items())),
        reasons=tuple(reasons),
        structurally_valid=not reasons or (
            set(reasons) == {"market_changed_or_unavailable_since_original_freeze"}
        ),
        all_original_lines_still_observed=bool(rows) and not reasons and
                                         all(row.status == "unchanged" for row in rows),
    )
