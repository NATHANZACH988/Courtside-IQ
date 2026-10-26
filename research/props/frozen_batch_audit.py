"""Read-only, full-denominator audit for frozen player-prop research selections.

A per-leg result checker cannot detect winners-only selection or omitted
losers. This module accounts for *every supplied frozen selection*, even when
its quote, final stat, or independent final-state receipt is missing.

IMPORTANT: The supplied frozen manifest, hashes, timestamps and source
receipts are claims, not authenticated evidence. The module does not certify
that the input manifest is the original complete pregame universe.
No settlement, model scoring, betting recommendation, network or file I/O.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from .final_chronology_audit import EventFinalReceipt, audit_prop_outcome_final
from .observed_outcome import ObservedPlayerStat
from .prop_board import Game, PropQuote, _digest, _id, _utc


@dataclass(frozen=True)
class FrozenPropSelection:
    """A declared pregame research selection of one exact posted quote."""
    selection_id: str
    quote_id: str
    frozen_at: datetime
    artifact_sha256: str

    def __post_init__(self) -> None:
        _id(self.selection_id, "selection_id")
        _id(self.quote_id, "quote_id")
        _digest(self.artifact_sha256, "artifact_sha256")
        object.__setattr__(self, "frozen_at", _utc(self.frozen_at, "frozen_at"))


@dataclass(frozen=True)
class FrozenPropRow:
    selection_id: str
    quote_id: str
    athlete_id: str | None
    market: str | None
    original_line: str | None
    original_side: str | None
    status: str
    reasons: tuple[str, ...]
    # No row is an authenticated sportsbook result or production grade.
    scoring_eligible: bool = False
    official_book_settlement_verified: bool = False


@dataclass(frozen=True)
class FrozenPropBatchAudit:
    event_id: str
    reviewed_at: datetime
    declared_frozen_denominator: int
    rows: tuple[FrozenPropRow, ...]
    pending: int
    unresolved: int
    invalid: int
    dnp_needs_rules: int
    pushes: int
    direction_matched: int
    direction_missed: int
    unselected_observation_records: int
    denominator_reconciled: bool
    structurally_valid: bool
    reasons: tuple[str, ...]
    source_independently_verified: bool = False
    manifest_completeness_verified: bool = False
    scoring_eligible: bool = False
    official_book_settlement_verified: bool = False
    model_accuracy_established: bool = False


def audit_frozen_prop_batch(
    game: Game,
    selections: tuple[FrozenPropSelection, ...],
    quotes: tuple[PropQuote, ...],
    observations: tuple[ObservedPlayerStat, ...],
    final_receipt: EventFinalReceipt | None,
    as_of: datetime,
) -> FrozenPropBatchAudit:
    """Account for each frozen selection; never silently omit unresolved legs.

    Selection/quote identity and freeze order are validated before calling
    the post-final audit. Multiple candidate stat receipts for the same
    player/event/market are ambiguous until versioned corrections are resolved.
    """
    if not isinstance(game, Game):
        raise TypeError("game must be Game")
    if (not isinstance(selections, tuple) or
            any(not isinstance(x, FrozenPropSelection) for x in selections)):
        raise TypeError("selections must be a tuple of FrozenPropSelection")
    if (not isinstance(quotes, tuple) or
            any(not isinstance(x, PropQuote) for x in quotes)):
        raise TypeError("quotes must be a tuple of PropQuote")
    if (not isinstance(observations, tuple) or
            any(not isinstance(x, ObservedPlayerStat) for x in observations)):
        raise TypeError("observations must be a tuple of ObservedPlayerStat")
    if final_receipt is not None and not isinstance(final_receipt, EventFinalReceipt):
        raise TypeError("final_receipt must be EventFinalReceipt or None")
    cutoff = _utc(as_of, "as_of")

    reasons: list[str] = []
    if not selections:
        reasons.append("frozen_selection_manifest_empty")
    if cutoff <= game.scheduled_start:
        reasons.append("batch_review_before_event_start")

    quotes_by_id: dict[str, list[PropQuote]] = {}
    for quote in quotes:
        quotes_by_id.setdefault(quote.quote_id, []).append(quote)

    obs_by_key: dict[tuple[str, str, str, str, str], list[ObservedPlayerStat]] = {}
    for obs in observations:
        key = (obs.event_id, obs.athlete_id, obs.team_id, obs.market, obs.period)
        obs_by_key.setdefault(key, []).append(obs)

    selection_ids = Counter(s.selection_id for s in selections)
    selected_quote_ids = Counter(s.quote_id for s in selections)
    used_observation_keys: set[tuple[str, str, str, str, str]] = set()
    rows: list[FrozenPropRow] = []

    for selection in selections:
        faults: list[str] = []
        if selection_ids[selection.selection_id] > 1:
            faults.append("duplicate_frozen_selection_id")
        if selected_quote_ids[selection.quote_id] > 1:
            faults.append("duplicate_selected_quote_id")
        if selection.frozen_at >= game.scheduled_start:
            faults.append("selection_frozen_at_or_after_tip")
        if selection.frozen_at > cutoff:
            faults.append("selection_frozen_after_review_cutoff")
        if cutoff <= game.scheduled_start:
            faults.append("batch_review_before_event_start")

        quote_candidates = quotes_by_id.get(selection.quote_id, [])
        if not quote_candidates:
            faults.append("original_quote_missing")
        elif len(quote_candidates) > 1:
            faults.append("ambiguous_original_quote_id")

        quote = quote_candidates[0] if len(quote_candidates) == 1 else None
        if quote is not None:
            if quote.event_id != game.event_id:
                faults.append("original_quote_event_mismatch")
            if quote.team_id not in {game.home_team_id, game.away_team_id}:
                faults.append("original_quote_team_not_in_event")
            if quote.source.captured_at > selection.frozen_at:
                faults.append("quote_captured_after_selection_freeze")
            if quote.source.captured_at >= game.scheduled_start:
                faults.append("quote_captured_at_or_after_tip")
            if quote.source.captured_at > cutoff:
                faults.append("quote_source_after_review_cutoff")

        status = "invalid" if faults else "pending"
        if quote is not None:
            key = (quote.event_id, quote.athlete_id, quote.team_id,
                   quote.market, quote.period)
            candidates = obs_by_key.get(key, [])
            used_observation_keys.add(key)
            if len(candidates) > 1:
                faults.append("ambiguous_stat_corrections_or_duplicate_observations")
                status = "invalid"
            elif len(candidates) == 1 and not faults:
                audited = audit_prop_outcome_final(
                    game, quote, candidates[0], final_receipt, cutoff,
                )
                if audited.structurally_valid:
                    status = audited.comparison
                else:
                    faults.extend(audited.reasons)
                    status = "invalid"
            elif len(candidates) == 0 and not faults:
                faults.append("player_outcome_missing")
                status = "pending"

        rows.append(FrozenPropRow(
            selection_id=selection.selection_id,
            quote_id=selection.quote_id,
            athlete_id=quote.athlete_id if quote is not None else None,
            market=quote.market if quote is not None else None,
            original_line=quote.line if quote is not None else None,
            original_side=quote.side if quote is not None else None,
            status=status,
            reasons=tuple(dict.fromkeys(faults)),
        ))

    unselected = sum(len(v) for k, v in obs_by_key.items()
                     if k not in used_observation_keys)
    if unselected:
        reasons.append("unselected_observations_excluded_from_denominator")
    if any(row.status == "invalid" for row in rows):
        reasons.append("invalid_frozen_selections_present")
    matched = {"selected_over", "selected_under"}
    missed = {"selected_over_lost", "selected_under_lost"}
    known_statuses = matched | missed | {
        "pending", "unresolved", "invalid", "dnp_needs_rules", "push",
    }
    reconciled = all(row.status in known_statuses for row in rows)
    if not reconciled:
        reasons.append("unrecognized_outcome_status")
    return FrozenPropBatchAudit(
        event_id=game.event_id, reviewed_at=cutoff,
        declared_frozen_denominator=len(selections),
        rows=tuple(rows),
        pending=sum(row.status == "pending" for row in rows),
        unresolved=sum(row.status == "unresolved" for row in rows),
        invalid=sum(row.status == "invalid" for row in rows),
        dnp_needs_rules=sum(row.status == "dnp_needs_rules" for row in rows),
        pushes=sum(row.status == "push" for row in rows),
        direction_matched=sum(row.status in matched for row in rows),
        direction_missed=sum(row.status in missed for row in rows),
        unselected_observation_records=unselected,
        denominator_reconciled=reconciled,
        structurally_valid=reconciled and
                           not any(row.status == "invalid" for row in rows) and
                           bool(selections) and cutoff > game.scheduled_start,
        reasons=tuple(reasons),
    )
