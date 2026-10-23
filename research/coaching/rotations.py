"""Coach-style rotation prediction baselines from observed substitutions."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from research.coaching.schemas import SubstitutionEvent


@dataclass(frozen=True)
class NextSubPrediction:
    team_id: str
    player_out_name: str
    predicted_in_name: str
    probability: float
    sample_size: int
    model_version: str
    verification: str  # inferred

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RotationForecast:
    team_id: str
    predictions: tuple[NextSubPrediction, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "predictions": [p.to_dict() for p in self.predictions],
            "notes": list(self.notes),
        }


def build_replacement_matrix(
    substitutions: list[SubstitutionEvent],
) -> dict[str, dict[str, Counter]]:
    """team -> player_out -> Counter(player_in)."""
    matrix: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for s in substitutions:
        if not s.player_out_name or not s.player_in_name:
            continue
        matrix[s.team_id][s.player_out_name][s.player_in_name] += 1
    return matrix


def predict_replacements(
    substitutions: list[SubstitutionEvent],
    *,
    min_samples: int = 1,
) -> list[RotationForecast]:
    """
    Frequency baseline: when player X sits, who usually enters?

    This is a transparent coach-behavior prior, not an optimal-lineup recommender.
    """
    matrix = build_replacement_matrix(substitutions)
    forecasts: list[RotationForecast] = []
    for team_id, by_out in matrix.items():
        preds: list[NextSubPrediction] = []
        for out_name, counter in by_out.items():
            total = sum(counter.values())
            if total < min_samples:
                continue
            in_name, count = counter.most_common(1)[0]
            preds.append(
                NextSubPrediction(
                    team_id=team_id,
                    player_out_name=out_name,
                    predicted_in_name=in_name,
                    probability=round(count / total, 3),
                    sample_size=total,
                    model_version="rotation-freq-v0",
                    verification="inferred",
                )
            )
        preds.sort(key=lambda p: (-p.sample_size, -p.probability, p.player_out_name))
        forecasts.append(
            RotationForecast(
                team_id=team_id,
                predictions=tuple(preds),
                notes=(
                    "Frequency baseline from this game's substitutions only.",
                    "Cross-game coach models require a multi-game point-in-time store.",
                    "Predicted coach behavior ≠ recommended optimal decision.",
                ),
            )
        )
    return forecasts


def compare_prediction_to_actual(
    prediction: NextSubPrediction,
    actual_in_name: str,
) -> dict[str, Any]:
    hit = prediction.predicted_in_name.lower() == actual_in_name.lower()
    return {
        "hit": hit,
        "predicted_in_name": prediction.predicted_in_name,
        "actual_in_name": actual_in_name,
        "probability": prediction.probability,
        "sample_size": prediction.sample_size,
        "model_version": prediction.model_version,
    }


def leave_one_out_accuracy(substitutions: list[SubstitutionEvent]) -> dict[str, Any]:
    """Simple LOO check within a single game (diagnostic, tiny sample)."""
    hits = 0
    total = 0
    details = []
    for i, actual in enumerate(substitutions):
        train = substitutions[:i] + substitutions[i + 1 :]
        forecasts = predict_replacements(train, min_samples=1)
        team_fc = next((f for f in forecasts if f.team_id == actual.team_id), None)
        if not team_fc:
            continue
        pred = next(
            (p for p in team_fc.predictions if p.player_out_name == actual.player_out_name),
            None,
        )
        if not pred:
            continue
        total += 1
        cmp = compare_prediction_to_actual(pred, actual.player_in_name)
        hits += int(cmp["hit"])
        details.append(cmp)
    return {
        "hits": hits,
        "total": total,
        "accuracy": round(hits / total, 3) if total else None,
        "details": details,
        "note": "Single-game LOO is illustrative only; not a validated coach model.",
    }
