"""Foul-trouble effects on projected minutes and opportunity."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean


@dataclass(frozen=True)
class FoulRateSample:
    game_id: str
    minutes: float
    personal_fouls: float
    period_fouls: tuple[float, ...] = ()  # optional per-quarter PF


@dataclass(frozen=True)
class FoulTroubleAssessment:
    fouls_per_36: float
    early_foul_rate: float
    projected_minutes_penalty: float
    opportunity_penalty: float
    notes: tuple[str, ...]
    verification: str  # inferred from game samples


def fouls_per_36(samples: list[FoulRateSample]) -> float:
    total_min = sum(s.minutes for s in samples)
    total_pf = sum(s.personal_fouls for s in samples)
    if total_min <= 0:
        return 0.0
    return round(36.0 * total_pf / total_min, 3)


def early_foul_pressure(samples: list[FoulRateSample]) -> float:
    """Share of fouls that arrived in Q1 when period data exists; else 0."""
    with_periods = [s for s in samples if s.period_fouls]
    if not with_periods:
        return 0.0
    ratios = []
    for s in with_periods:
        total = sum(s.period_fouls) or 1.0
        ratios.append(s.period_fouls[0] / total)
    return round(mean(ratios), 3)


def assess_foul_trouble(samples: list[FoulRateSample]) -> FoulTroubleAssessment:
    """
    Infer minute/opportunity pressure from foul rates.

    Heuristic (transparent, not a betting claim):
    - Baseline PF/36 around 3.0 is neutral.
    - Each +1.0 PF/36 above 3.0 trims ~1.5 projected minutes.
    - Elevated early-foul share adds extra minute risk.
    """
    if not samples:
        return FoulTroubleAssessment(
            fouls_per_36=0.0,
            early_foul_rate=0.0,
            projected_minutes_penalty=0.0,
            opportunity_penalty=0.0,
            notes=("No foul samples; no penalty applied.",),
            verification="assumed",
        )

    pf36 = fouls_per_36(samples)
    early = early_foul_pressure(samples)
    excess = max(0.0, pf36 - 3.0)
    minute_penalty = round(excess * 1.5 + early * 2.0, 2)
    # Opportunity (usage proxy) softens slightly with foul risk — caps at 0.15
    opp_penalty = round(min(0.15, excess * 0.04 + early * 0.05), 3)
    notes = [
        f"PF/36={pf36} across {len(samples)} games.",
        f"Early-foul share={early}.",
        f"Projected minutes penalty={minute_penalty}.",
        f"Opportunity penalty={opp_penalty}.",
    ]
    return FoulTroubleAssessment(
        fouls_per_36=pf36,
        early_foul_rate=early,
        projected_minutes_penalty=minute_penalty,
        opportunity_penalty=opp_penalty,
        notes=tuple(notes),
        verification="inferred",
    )


def apply_foul_penalty(base_minutes: float, assessment: FoulTroubleAssessment) -> float:
    return round(max(0.0, float(base_minutes) - assessment.projected_minutes_penalty), 2)
