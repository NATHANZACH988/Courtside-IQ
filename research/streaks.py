"""Hot / cold streak detection and teammate spillover effects."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev


@dataclass(frozen=True)
class StatGame:
    game_id: str
    value: float
    minutes: float


@dataclass(frozen=True)
class StreakAssessment:
    label: str  # hot | cold | neutral
    window: int
    window_mean: float
    season_mean: float
    z_score: float
    self_adjustment: float
    teammate_spillover: float
    notes: tuple[str, ...]
    verification: str


def _z(window_mean: float, season_mean: float, season_sd: float) -> float:
    if season_sd <= 1e-9:
        return 0.0
    return (window_mean - season_mean) / season_sd


def assess_streak(
    games: list[StatGame],
    *,
    window: int = 5,
    hot_z: float = 1.0,
    cold_z: float = -1.0,
) -> StreakAssessment:
    """
    Compare trailing window mean vs season distribution.

    Adjustments are explanatory priors for research, not Arena scoring inputs.
    Hot streaks slightly raise self projection; cold streaks lower it.
    Teammate spillover models usage redistribution (hot scorer can crowd teammates;
    cold scorer can free them). Magnitudes are intentionally modest.
    """
    if len(games) < 2:
        return StreakAssessment(
            label="neutral",
            window=window,
            window_mean=0.0,
            season_mean=0.0,
            z_score=0.0,
            self_adjustment=0.0,
            teammate_spillover=0.0,
            notes=("Insufficient games for streak assessment.",),
            verification="assumed",
        )

    values = [g.value for g in games]
    season_mean = mean(values)
    season_sd = pstdev(values) if len(values) > 1 else 0.0
    recent = values[-window:]
    w_mean = mean(recent)
    z = round(_z(w_mean, season_mean, season_sd), 3)

    if z >= hot_z:
        label = "hot"
        self_adj = round(min(0.12, z * 0.04), 3)
        spillover = round(-min(0.08, z * 0.025), 3)  # crowds teammates
    elif z <= cold_z:
        label = "cold"
        self_adj = round(max(-0.12, z * 0.04), 3)
        spillover = round(min(0.08, abs(z) * 0.025), 3)  # frees teammates
    else:
        label = "neutral"
        self_adj = 0.0
        spillover = 0.0

    notes = (
        f"Window-{len(recent)} mean={round(w_mean, 2)} vs season mean={round(season_mean, 2)}.",
        f"z={z}; label={label}.",
        f"Self adjustment factor={self_adj}; teammate spillover={spillover}.",
        "Spillover is an opportunity prior for teammates, not a guarantee.",
    )
    return StreakAssessment(
        label=label,
        window=len(recent),
        window_mean=round(w_mean, 3),
        season_mean=round(season_mean, 3),
        z_score=z,
        self_adjustment=self_adj,
        teammate_spillover=spillover,
        notes=notes,
        verification="inferred",
    )


def apply_streak_to_projection(base: float, assessment: StreakAssessment) -> float:
    return round(float(base) * (1.0 + assessment.self_adjustment), 2)


def apply_teammate_spillover(teammate_base: float, star_assessment: StreakAssessment) -> float:
    return round(float(teammate_base) * (1.0 + star_assessment.teammate_spillover), 2)
