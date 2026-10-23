"""Parse ESPN play-by-play into substitution / foul / shot features."""

from __future__ import annotations

import re
from typing import Any

from research.coaching.schemas import (
    FoulState,
    HotColdState,
    Provenance,
    SubstitutionEvent,
)

SUB_RE = re.compile(
    r"^(?P<inn>.+?) enters the game for (?P<out>.+)$",
    re.IGNORECASE,
)


def iter_plays(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return list(summary.get("plays") or [])


def extract_substitutions(
    game_id: str,
    summary: dict[str, Any],
) -> list[SubstitutionEvent]:
    out: list[SubstitutionEvent] = []
    for play in iter_plays(summary):
        type_text = (play.get("type") or {}).get("text") or ""
        text = play.get("text") or ""
        if type_text != "Substitution" and "enters the game for" not in text.lower():
            continue
        m = SUB_RE.match(text.strip())
        if not m:
            continue
        team = ((play.get("team") or {}).get("abbreviation")) or ""
        period = int((play.get("period") or {}).get("number") or 0)
        clock = (play.get("clock") or {}).get("displayValue") or ""
        # Heuristic reason: recent foul on outgoing player is not wired yet
        out.append(
            SubstitutionEvent(
                game_id=game_id,
                period=period,
                clock=clock,
                team_id=team,
                player_in_id=None,
                player_in_name=m.group("inn").strip(),
                player_out_id=None,
                player_out_name=m.group("out").strip(),
                score_margin=_margin(play),
                reason_hint="unknown",
                source_event_text=text,
                verification="verified",
            )
        )
    return out


def extract_foul_states(game_id: str, summary: dict[str, Any]) -> list[FoulState]:
    """Running personal-foul tallies inferred from foul play text."""
    tallies: dict[str, int] = {}
    events: list[FoulState] = []
    for play in iter_plays(summary):
        type_text = (play.get("type") or {}).get("text") or ""
        text = play.get("text") or ""
        if "foul" not in type_text.lower() and "foul" not in text.lower():
            continue
        # Typical: "Matas Buzelis shooting foul"
        name = text
        for suffix in (
            " shooting foul",
            " personal foul",
            " loose ball foul",
            " offensive foul",
            " technical foul",
            " flagrant foul",
            " foul",
        ):
            if name.lower().endswith(suffix):
                name = name[: -len(suffix)]
                break
        name = name.strip()
        if not name:
            continue
        tallies[name] = tallies.get(name, 0) + 1
        pf = tallies[name]
        # Simple foul-out risk prior: rises sharply near 5/6
        risk = min(1.0, max(0.0, (pf - 2) / 4.0))
        events.append(
            FoulState(
                player_id=f"name:{name}",
                game_id=game_id,
                period=int((play.get("period") or {}).get("number") or 0),
                clock=(play.get("clock") or {}).get("displayValue") or "",
                personal_fouls=pf,
                team_fouls_period=None,
                minutes_played=None,
                foul_out_risk=round(risk, 3),
                verification="inferred",
            )
        )
    return events


def extract_hot_cold_from_shots(
    game_id: str,
    summary: dict[str, Any],
    *,
    window: int = 8,
) -> list[HotColdState]:
    """Trailing make/miss windows from shot plays — not a validated hot-hand claim."""
    by_player: dict[str, list[bool]] = {}
    for play in iter_plays(summary):
        type_text = (play.get("type") or {}).get("text") or ""
        text = play.get("text") or ""
        if "Shot" not in type_text and "shot" not in text.lower():
            continue
        if "Free Throw" in type_text:
            continue
        # ESPN scoringPlay / shot result
        made = bool(play.get("scoringPlay")) or " makes " in f" {text.lower()} "
        miss = "miss" in text.lower()
        if not made and not miss:
            continue
        # crude name: text often starts with player name
        name = text.split(" ")[0:3]
        # Better: athletes in play
        athletes = play.get("participants") or play.get("athletesInvolved") or []
        if athletes:
            pname = (athletes[0].get("athlete") or athletes[0]).get("displayName") or " ".join(name)
        else:
            pname = text.split(" ")[0]
            # try first two tokens if capitalized
            parts = text.split()
            if len(parts) >= 2 and parts[1][:1].isupper():
                pname = f"{parts[0]} {parts[1]}"
        by_player.setdefault(pname, []).append(bool(made and not miss))

    states: list[HotColdState] = []
    for pname, seq in by_player.items():
        recent = seq[-window:]
        if len(recent) < 4:
            continue
        makes = sum(1 for x in recent if x)
        attempts = len(recent)
        pct = makes / attempts if attempts else None
        if pct is not None and pct >= 0.625 and makes >= 4:
            label = "hot"
            note = "High recent FG% in short window; may be variance or quality shift."
        elif pct is not None and pct <= 0.25 and attempts >= 5:
            label = "cold"
            note = "Low recent FG% in short window; do not assume persistence."
        else:
            label = "neutral"
            note = "Within noise band vs simple FG% thresholds."
        states.append(
            HotColdState(
                player_id=f"name:{pname}",
                game_id=game_id,
                window_makes=makes,
                window_attempts=attempts,
                window_fg_pct=round(pct, 3) if pct is not None else None,
                label=label,  # type: ignore[arg-type]
                mechanism_note=note,
                verification="inferred",
            )
        )
    return states


def build_provenance(source_url: str, fetched_at_utc: str) -> Provenance:
    return Provenance(
        source_url=source_url,
        fetched_at_utc=fetched_at_utc,
        model_version="coaching-pbp-v0",
        coverage_notes="ESPN public play-by-play; no tracking/film inputs.",
    )


def _margin(play: dict[str, Any]) -> int | None:
    # ESPN plays sometimes include homeScore/awayScore
    if "homeScore" in play and "awayScore" in play:
        try:
            return int(play["homeScore"]) - int(play["awayScore"])
        except (TypeError, ValueError):
            return None
    return None
