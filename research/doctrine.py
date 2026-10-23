"""Research doctrine helpers — Play / Lean / Pass gates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


MIN_BANKED_GAMES_FOR_PLAY = 5


class Verdict(str, Enum):
    PLAY = "Play"
    LEAN = "Lean"
    PASS = "Pass"


@dataclass(frozen=True)
class VerdictDecision:
    verdict: Verdict
    reason: str
    banked_games: int
    owner_override: bool


def decide_verdict(
    banked_current_season_games: int,
    *,
    opportunity_rank_ok: bool,
    evidence_strength: float,
    owner_override: bool = False,
) -> VerdictDecision:
    """Apply doctrine gates. Does not claim betting performance."""
    n = int(banked_current_season_games)
    if n < MIN_BANKED_GAMES_FOR_PLAY and not owner_override:
        return VerdictDecision(
            verdict=Verdict.PASS,
            reason=(
                f"Fewer than {MIN_BANKED_GAMES_FOR_PLAY} banked current-season games "
                f"({n}); Play blocked without owner override."
            ),
            banked_games=n,
            owner_override=False,
        )
    if not opportunity_rank_ok:
        return VerdictDecision(
            verdict=Verdict.PASS,
            reason="Opportunity/usage rank does not support a positive call.",
            banked_games=n,
            owner_override=owner_override,
        )
    if evidence_strength >= 0.75:
        return VerdictDecision(
            verdict=Verdict.PLAY,
            reason="Opportunity + evidence strength meet Play threshold.",
            banked_games=n,
            owner_override=owner_override,
        )
    if evidence_strength >= 0.55:
        return VerdictDecision(
            verdict=Verdict.LEAN,
            reason="Moderate evidence; Lean only.",
            banked_games=n,
            owner_override=owner_override,
        )
    return VerdictDecision(
        verdict=Verdict.PASS,
        reason="Evidence strength below Lean threshold.",
        banked_games=n,
        owner_override=owner_override,
    )
