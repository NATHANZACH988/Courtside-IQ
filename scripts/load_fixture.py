"""Helpers to load attributed offline box-score fixtures."""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "box_scores"


def load_box_score(name: str = "2024-01-15-bos-ind.json") -> dict:
    path = FIXTURES_DIR / name
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("source_url"):
        raise ValueError(f"Fixture {name} missing source_url")
    if not data.get("fetched_at_utc"):
        raise ValueError(f"Fixture {name} missing fetched_at_utc")
    return data


def player_stat(fixture: dict, player_id: str, stat: str) -> float:
    for p in fixture["players"]:
        if p["player_id"] == player_id:
            if stat not in p:
                raise KeyError(f"{stat} not in fixture for {player_id}")
            return float(p[stat])
    raise KeyError(player_id)
