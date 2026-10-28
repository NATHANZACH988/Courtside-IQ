"""Offline ESPN NBA summary-to-watcher capture-loss audit.

Read-only research diagnostic. Both documents are caller supplied; this does
not fetch ESPN, attest source authenticity, or authorize a player-prop Play.
Only fields actually present in the source can be classified as discarded.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _path(doc: dict, *keys: str | int) -> Any:
    cur: Any = doc
    for key in keys:
        if isinstance(cur, dict) and isinstance(key, str):
            cur = cur.get(key)
        elif isinstance(cur, list) and isinstance(key, int) and 0 <= key < len(cur):
            cur = cur[key]
        else:
            return None
    return cur


def _first_list(doc: dict, paths: tuple[tuple[str | int, ...], ...]) -> list:
    for path in paths:
        value = _path(doc, *path)
        if isinstance(value, list) and value:
            return value
    return []


def _count(source: int, stored: int, *, equal: bool = True) -> dict:
    if not source:
        status = "not_in_source"
    elif stored == 0:
        status = "discarded"
    elif stored < source:
        status = "partial"
    elif stored > source or not equal:
        status = "altered_or_unreconciled"
    else:
        status = "retained"
    return {"source_items": source, "captured_items": stored, "status": status}


def _raw_players(raw: dict) -> dict[tuple[str, str], dict]:
    rows: dict[tuple[str, str], dict] = {}
    for group in _path(raw, "boxscore", "players") or []:
        if not isinstance(group, dict):
            raise ValueError("invalid source player group")
        team = _path(group, "team", "abbreviation")
        for stat_group in group.get("statistics", [])[:1]:
            labels = stat_group.get("labels", [])
            if not isinstance(labels, list):
                raise ValueError("invalid player labels")
            for row in stat_group.get("athletes", []):
                name = _path(row, "athlete", "displayName")
                if not isinstance(team, str) or not isinstance(name, str):
                    raise ValueError("source player identity missing")
                key = (team, name)
                if key in rows:
                    raise ValueError("ambiguous source player identity")
                values = row.get("stats", [])
                if not isinstance(values, list):
                    raise ValueError("invalid player stats")
                rows[key] = dict(zip(labels, values))
    return rows


def _captured_players(captured: dict) -> dict[tuple[str, str], dict]:
    rows: dict[tuple[str, str], dict] = {}
    for row in captured.get("players", []):
        if not isinstance(row, dict):
            raise ValueError("invalid captured player")
        key = (row.get("team"), row.get("name"))
        if not all(isinstance(v, str) and v for v in key):
            raise ValueError("captured player identity missing")
        if key in rows:
            raise ValueError("ambiguous captured player identity")
        rows[key] = row
    return rows


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
        return number if str(value).strip() == str(number) else None
    except (ValueError, TypeError):
        return None


def _made_attempted(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, str) or "-" not in value:
        return None
    made, attempted = value.split("-", 1)
    m, a = _integer(made), _integer(attempted)
    if m is None or a is None or m < 0 or a < m:
        return None
    return m, a


def _stat_coverage(raw_players: dict, stored_players: dict, label: str,
                   aliases: tuple[str, ...]) -> dict:
    """Keep absent, partially retained and corrupted player stats distinct.

    A captured value that disagrees with the source is not discarded: it is
    altered/unreconciled. Counts describe rows with at least one stored field,
    not merely rows whose values happen to match the supplied source.
    """
    observed = 0
    captured = 0
    retained = 0
    partial = 0
    altered = 0
    for identity, stats in raw_players.items():
        if label not in stats:
            continue
        expected = (_made_attempted(stats[label]) if label in ("3PT", "FT")
                    else _integer(stats[label]))
        if expected is None:
            continue
        observed += 1
        player = stored_players.get(identity)
        if player is None:
            continue
        present = [key in player for key in aliases]
        if not any(present):
            continue
        captured += 1
        if not all(present):
            partial += 1
            continue
        actual = tuple(_integer(player[key]) for key in aliases)
        if (actual == expected if label in ("3PT", "FT")
                else len(actual) == 1 and actual[0] == expected):
            retained += 1
        else:
            altered += 1

    if not observed:
        status = "not_in_source"
    elif altered:
        status = "altered_or_unreconciled"
    elif retained == observed:
        status = "retained"
    elif not captured:
        status = "discarded"
    else:
        status = "partial"
    return {
        "source_items": observed,
        "captured_items": captured,
        "retained_items": retained,
        "partial_items": partial,
        "altered_items": altered,
        "status": status,
    }


def audit_nba_summary_capture(raw: dict, captured: dict) -> dict:
    """Compare a source summary and compact watcher output for the same game.

    Values are checked for player box stats and full lists for plays/officials/
    team stats. Identity uses team + display name, so trades/duplicate names
    need a future athlete-ID-based reconciliation. No network or file writes.
    """
    if not isinstance(raw, dict) or not isinstance(captured, dict):
        raise TypeError("source and capture must be JSON objects")
    event = (_path(raw, "header", "id")
             or _path(raw, "header", "competitions", 0, "id")
             or raw.get("event_id"))
    stored_event = captured.get("event", captured.get("event_id"))
    if not event or str(event) != str(stored_event):
        raise ValueError("missing or mismatched event identity")

    source_plays = _first_list(raw, (("plays",),))
    stored_plays = _first_list(captured, (("plays",), ("play_by_play",)))
    source_officials = _first_list(
        raw, (("officials",), ("header", "competitions", 0, "officials")))
    stored_officials = _first_list(captured, (("officials",),))
    source_teams = [
        team for team in (_path(raw, "boxscore", "teams") or [])
        if isinstance(team, dict) and team.get("statistics")
    ]
    stored_teams = _first_list(captured, (("team_stats",), ("team_statistics",)))
    sections = {
        "play_by_play": _count(len(source_plays), len(stored_plays),
                               equal=source_plays == stored_plays),
        "officials": _count(len(source_officials), len(stored_officials),
                            equal=source_officials == stored_officials),
        "team_statistics": _count(len(source_teams), len(stored_teams),
                                  equal=source_teams == stored_teams),
    }

    def clock(play: Any) -> Any:
        return play.get("clock") if isinstance(play, dict) else None

    def coordinate(play: Any) -> Any:
        if not isinstance(play, dict):
            return None
        for key in ("coordinate", "shotCoordinate"):
            value = play.get(key)
            if isinstance(value, dict) and "x" in value and "y" in value:
                return value
        return None

    for label, extractor in (("play_clocks", clock),
                             ("shot_coordinates", coordinate)):
        source_values = [extractor(p) for p in source_plays if extractor(p) is not None]
        stored_values = [extractor(p) for p in stored_plays if extractor(p) is not None]
        sections[label] = _count(len(source_values), len(stored_values),
                                 equal=source_values == stored_values)

    source_players = _raw_players(raw)
    stored_players = _captured_players(captured)
    for label, aliases in {
        "AST": ("ast",),
        "3PT": ("threes", "three_attempts"),
        "STL": ("stl",),
        "BLK": ("blk",),
        "TO": ("to",),
        "FT": ("ftm", "fta"),
    }.items():
        sections["player_" + label.lower()] = _stat_coverage(
            source_players, stored_players, label, aliases)

    lost = sorted(key for key, value in sections.items()
                  if value["status"] not in ("retained", "not_in_source"))
    unavailable = sorted(key for key, value in sections.items()
                         if value["status"] == "not_in_source")
    return {
        "event_id": str(event),
        "canonical_supplied_source_sha256": hashlib.sha256(
            _json(raw).encode("utf-8")).hexdigest(),
        "sections": sections,
        "lost_or_unreconciled": lost,
        "not_in_source": unavailable,
        "available_fields_structurally_retained": not lost,
        "complete_source_surface_observed": not unavailable,
        "source_authenticity_verified": False,
        "player_prop_scoring_authorized": False,
    }
