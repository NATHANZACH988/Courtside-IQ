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


def _ordered_subset_coverage(source_items: list, captured_items: list) -> dict:
    """Only classify a shorter officials/team-stat capture as partial if exact.

    Counts alone are insufficient: a shortened list may contain fabricated or
    modified records. Preserve source order and require exact JSON equality.
    Unlike plays, these generic surfaces have no independently validated ID.
    """
    source_count, captured_count = len(source_items), len(captured_items)
    if not source_count:
        return {"source_items": 0, "captured_items": captured_count,
                "status": "altered_or_unreconciled" if captured_count
                else "not_in_source"}
    if not captured_count:
        return _count(source_count, 0)
    if captured_count > source_count:
        return {"source_items": source_count, "captured_items": captured_count,
                "status": "altered_or_unreconciled"}

    cursor = 0
    for item in captured_items:
        while cursor < source_count and source_items[cursor] != item:
            cursor += 1
        if cursor == source_count:
            return {"source_items": source_count, "captured_items": captured_count,
                    "status": "altered_or_unreconciled"}
        cursor += 1
    return _count(source_count, captured_count)


def _raw_players(raw: dict) -> dict[tuple[str, str], dict]:
    rows: dict[tuple[str, str], dict] = {}
    for group in _path(raw, "boxscore", "players") or []:
        if not isinstance(group, dict):
            raise ValueError("invalid source player group")
        team = _path(group, "team", "abbreviation")
        # ESPN may split a team's athletes across multiple stat groups
        # (for example, starters and reserves). Ignoring later groups can
        # falsely certify a full-roster capture while omitting bench players.
        for stat_group in group.get("statistics", []):
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
                if (any(not isinstance(label, str) or not label for label in labels)
                        or len(set(labels)) != len(labels)):
                    raise ValueError("invalid or duplicate source stat labels")
                # zip() silently truncates a malformed row, which can make
                # available source stats appear absent rather than corrupted.
                # ESPN may legitimately omit all stats for a DNP athlete.
                if len(values) != len(labels):
                    if not values and row.get("didNotPlay") is True:
                        rows[key] = {}
                        continue
                    raise ValueError("source player labels/stats length mismatch")
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
        # A missing component is partial only if every component actually
        # captured matches the supplied source. Otherwise a wrong make/attempt
        # value can be laundered into an innocent-looking partial capture.
        expected_values = expected if isinstance(expected, tuple) else (expected,)
        actual_values = tuple(_integer(player[key]) if key in player else None
                              for key in aliases)
        if any(is_present and actual_values[index] != expected_values[index]
               for index, is_present in enumerate(present)):
            altered += 1
        elif not all(present):
            partial += 1
        else:
            retained += 1

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


def _play_coverage(source_plays: list, stored_plays: list) -> dict:
    """Classify a partial play capture only when every retained play is exact.

    Counts alone cannot distinguish a genuine subset from fabricated or
    altered events. A stable, unique play ID is required for reconciliation.
    """
    source_count, stored_count = len(source_plays), len(stored_plays)
    if not source_count:
        return {"source_items": 0, "captured_items": stored_count,
                "status": "altered_or_unreconciled" if stored_count else "not_in_source"}
    if not stored_count:
        return _count(source_count, 0)
    if not all(isinstance(p, dict) and p.get("id") is not None
               for p in source_plays + stored_plays):
        return _count(source_count, stored_count, equal=False) | {
            "status": "altered_or_unreconciled"
        }
    source_ids = [str(p["id"]) for p in source_plays]
    stored_ids = [str(p["id"]) for p in stored_plays]
    if len(set(source_ids)) != source_count or len(set(stored_ids)) != stored_count:
        return {"source_items": source_count, "captured_items": stored_count,
                "status": "altered_or_unreconciled"}
    index = {key: i for i, key in enumerate(source_ids)}
    positions = [index.get(key) for key in stored_ids]
    valid = (all(pos is not None for pos in positions)
             and positions == sorted(positions)
             and all(source_plays[pos] == play
                     for pos, play in zip(positions, stored_plays)))
    if not valid or stored_count > source_count:
        return {"source_items": source_count, "captured_items": stored_count,
                "status": "altered_or_unreconciled"}
    return _count(source_count, stored_count)


def _play_field_coverage(source_plays: list, stored_plays: list, extractor) -> dict:
    """Bind a clock or coordinate to its play ID, not just its list position."""
    source = [(str(p.get("id")) if isinstance(p, dict) else None, extractor(p))
              for p in source_plays if extractor(p) is not None]
    stored = [(str(p.get("id")) if isinstance(p, dict) else None, extractor(p))
              for p in stored_plays if extractor(p) is not None]
    if not source:
        return {"source_items": 0, "captured_items": len(stored),
                "status": "altered_or_unreconciled" if stored else "not_in_source"}
    if not stored:
        return _count(len(source), 0)
    source_ids = [identity for identity, _ in source]
    stored_ids = [identity for identity, _ in stored]
    if (None in source_ids or None in stored_ids
            or len(set(source_ids)) != len(source_ids)
            or len(set(stored_ids)) != len(stored_ids)):
        return {"source_items": len(source), "captured_items": len(stored),
                "status": "altered_or_unreconciled"}
    expected = dict(source)
    if any(identity not in expected or expected[identity] != value
           for identity, value in stored):
        return {"source_items": len(source), "captured_items": len(stored),
                "status": "altered_or_unreconciled"}
    return _count(len(source), len(stored))


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
        "play_by_play": _play_coverage(source_plays, stored_plays),
        "officials": _ordered_subset_coverage(source_officials, stored_officials),
        "team_statistics": _ordered_subset_coverage(source_teams, stored_teams),
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
        sections[label] = _play_field_coverage(source_plays, stored_plays, extractor)

    source_players = _raw_players(raw)
    stored_players = _captured_players(captured)

    # A forged or misattributed player must not disappear from the audit just
    # because the source players' individual stat fields match. Treat the
    # identity universe as an independently reconciled evidence section.
    source_ids, captured_ids = set(source_players), set(stored_players)
    matched = source_ids & captured_ids
    missing = source_ids - captured_ids
    unexpected = captured_ids - source_ids
    if unexpected:
        player_status = "altered_or_unreconciled"
    elif not source_ids:
        player_status = "not_in_source"
    elif not matched:
        player_status = "discarded"
    elif missing:
        player_status = "partial"
    else:
        player_status = "retained"
    sections["player_identity"] = {
        "source_items": len(source_ids),
        "captured_items": len(captured_ids),
        "matched_items": len(matched),
        "missing_items": len(missing),
        "unexpected_items": len(unexpected),
        "status": player_status,
    }
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
