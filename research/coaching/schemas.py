"""Source-attributed game-state schemas for coaching intelligence.

Arena scoring does not consume subjective grades. Frozen contest baselines
never change after lock.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Verification = Literal["verified", "inferred", "assumed"]


@dataclass(frozen=True)
class Provenance:
    source_url: str
    fetched_at_utc: str
    model_version: str
    coverage_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PlayerGrade:
    player_id: str
    game_id: str
    role: str
    offense_grade: float  # 0–100 role-adjusted, not a betting claim
    defense_grade: float
    decision_grade: float
    box_outcome_grade: float
    evidence_coverage: float  # 0–1
    verification: Verification
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FoulState:
    player_id: str
    game_id: str
    period: int
    clock: str
    personal_fouls: int
    team_fouls_period: int | None
    minutes_played: float | None
    foul_out_risk: float  # 0–1 inferred
    verification: Verification

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SubstitutionEvent:
    game_id: str
    period: int
    clock: str
    team_id: str
    player_in_id: str | None
    player_in_name: str
    player_out_id: str | None
    player_out_name: str
    score_margin: int | None
    reason_hint: str | None  # foul | fatigue | matchup | unknown
    source_event_text: str
    verification: Verification = "verified"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RotationStint:
    game_id: str
    team_id: str
    player_id: str | None
    player_name: str
    period_start: int
    clock_start: str
    period_end: int | None
    clock_end: str | None
    seconds_approx: float | None
    verification: Verification

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FatigueProxy:
    player_id: str
    game_id: str
    minutes: float
    stint_count: int
    longest_stint_seconds: float | None
    back_to_back: bool
    fatigue_index: float  # 0–1 heuristic
    verification: Verification
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HotColdState:
    player_id: str
    game_id: str
    window_makes: int
    window_attempts: int
    window_fg_pct: float | None
    label: Literal["hot", "cold", "neutral"]
    mechanism_note: str
    verification: Verification

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GameStateBundle:
    game_id: str
    provenance: Provenance
    substitutions: list[SubstitutionEvent] = field(default_factory=list)
    foul_events: list[FoulState] = field(default_factory=list)
    stints: list[RotationStint] = field(default_factory=list)
    fatigue: list[FatigueProxy] = field(default_factory=list)
    hot_cold: list[HotColdState] = field(default_factory=list)
    grades: list[PlayerGrade] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "provenance": self.provenance.to_dict(),
            "substitutions": [s.to_dict() for s in self.substitutions],
            "foul_events": [f.to_dict() for f in self.foul_events],
            "stints": [s.to_dict() for s in self.stints],
            "fatigue": [f.to_dict() for f in self.fatigue],
            "hot_cold": [h.to_dict() for h in self.hot_cold],
            "grades": [g.to_dict() for g in self.grades],
        }
