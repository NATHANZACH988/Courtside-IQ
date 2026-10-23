"""Rotation / minutes projection helpers combining foul + role signals."""

from __future__ import annotations

from dataclasses import dataclass

from research.foul_trouble import FoulTroubleAssessment, apply_foul_penalty


@dataclass(frozen=True)
class MinutesProjection:
    base_minutes: float
    after_foul_penalty: float
    injury_adjustment: float
    projected_minutes: float
    notes: tuple[str, ...]


def project_minutes(
    base_minutes: float,
    foul: FoulTroubleAssessment,
    *,
    injury_minutes_delta: float = 0.0,
) -> MinutesProjection:
    after_foul = apply_foul_penalty(base_minutes, foul)
    projected = round(max(0.0, after_foul + injury_minutes_delta), 2)
    notes = [
        f"Base minutes={base_minutes}.",
        f"After foul penalty={after_foul}.",
        f"Injury delta={injury_minutes_delta}.",
        f"Projected={projected}.",
    ]
    return MinutesProjection(
        base_minutes=float(base_minutes),
        after_foul_penalty=after_foul,
        injury_adjustment=float(injury_minutes_delta),
        projected_minutes=projected,
        notes=tuple(notes),
    )
