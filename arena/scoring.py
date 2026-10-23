"""Deterministic closeness scoring (closeness-v1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

SCORING_VERSION = "closeness-v1"

# Absolute-error scales: score reaches 0 when |error| >= scale.
STAT_SCALES: Mapping[str, float] = {
    "PTS": 12.0,
    "REB": 6.0,
    "AST": 5.0,
    "FG3M": 3.0,
    "STL": 2.5,
    "BLK": 2.5,
    "TOV": 3.0,
}

PROVISIONAL_SAMPLE_THRESHOLD = 5


class UnsupportedStatError(ValueError):
    pass


@dataclass(frozen=True)
class GradeResult:
    score: float
    baseline_score: float
    skill_delta: float
    scoring_version: str
    error: float
    baseline_error: float


def closeness_score(predicted: float, actual: float, stat: str) -> float:
    """Return 0–100 closeness score for a single prediction."""
    scale = STAT_SCALES.get(stat.upper())
    if scale is None:
        raise UnsupportedStatError(f"Unsupported stat for scoring: {stat}")
    error = abs(float(predicted) - float(actual))
    raw = 100.0 * (1.0 - error / scale)
    return round(max(0.0, raw), 2)


def grade_prediction(
    predicted: float,
    actual: float,
    baseline: float,
    stat: str,
    *,
    scoring_version: str = SCORING_VERSION,
) -> GradeResult:
    if scoring_version != SCORING_VERSION:
        raise ValueError(f"Unsupported scoring_version: {scoring_version}")
    score = closeness_score(predicted, actual, stat)
    baseline_score = closeness_score(baseline, actual, stat)
    return GradeResult(
        score=score,
        baseline_score=baseline_score,
        skill_delta=round(score - baseline_score, 2),
        scoring_version=scoring_version,
        error=round(abs(float(predicted) - float(actual)), 4),
        baseline_error=round(abs(float(baseline) - float(actual)), 4),
    )


def is_provisional(completed_count: int) -> bool:
    return int(completed_count) < PROVISIONAL_SAMPLE_THRESHOLD
