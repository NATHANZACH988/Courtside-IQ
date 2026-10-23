"""ESPN public JSON fetcher with source attribution.

Commercial-use rights for production deployment are NOT verified here.
Beta/research fetches must preserve source_url + fetched_at_utc and must
never invent statistics when a fetch fails.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

USER_AGENT = "CourtsideIQ-Beta/0.1 (+https://github.com/NATHANZACH988/Courtside-IQ; research)"
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={event_id}"


class LiveFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class FetchedDocument:
    source_url: str
    fetched_at_utc: str
    payload: dict[str, Any]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_json(url: str, *, timeout: float = 15.0) -> FetchedDocument:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise LiveFetchError(f"Failed to fetch {url}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LiveFetchError(f"Invalid JSON from {url}") from exc
    return FetchedDocument(source_url=url, fetched_at_utc=_now_iso(), payload=payload)


def fetch_scoreboard() -> FetchedDocument:
    return fetch_json(SCOREBOARD_URL)


def fetch_game_summary(event_id: str) -> FetchedDocument:
    return fetch_json(SUMMARY_URL.format(event_id=event_id))


def parse_box_players(summary: dict[str, Any]) -> list[dict[str, Any]]:
    players: list[dict[str, Any]] = []
    for team in summary.get("boxscore", {}).get("players", []):
        ab = team.get("team", {}).get("abbreviation")
        for cat in team.get("statistics", []):
            keys = cat.get("keys") or []
            for ath in cat.get("athletes", []):
                d = dict(zip(keys, ath.get("stats", [])))
                a = ath.get("athlete", {})
                threes = str(d.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted", "0-0"))
                players.append(
                    {
                        "player_id": f"espn_{a.get('id')}",
                        "full_name": a.get("displayName"),
                        "team_id": ab,
                        "minutes": float(d.get("minutes") or 0),
                        "PTS": int(d.get("points") or 0),
                        "REB": int(d.get("rebounds") or 0),
                        "AST": int(d.get("assists") or 0),
                        "FG3M": int(threes.split("-")[0] or 0),
                        "STL": int(d.get("steals") or 0),
                        "BLK": int(d.get("blocks") or 0),
                        "TOV": int(d.get("turnovers") or 0),
                        "PF": int(d.get("fouls") or 0),
                        "starter": bool(ath.get("starter")),
                    }
                )
    return players


def parse_game_meta(summary: dict[str, Any]) -> dict[str, Any]:
    header = summary.get("header", {})
    comps = header.get("competitions") or [{}]
    comp = comps[0]
    competitors = comp.get("competitors") or []
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})
    status = (comp.get("status") or {}).get("type") or {}
    return {
        "game_id": f"espn_{header.get('id') or comp.get('id')}",
        "espn_event_id": str(header.get("id") or ""),
        "season": str((header.get("season") or {}).get("year") or ""),
        "home_team_id": (home.get("team") or {}).get("abbreviation"),
        "away_team_id": (away.get("team") or {}).get("abbreviation"),
        "home_score": int(home.get("score") or 0),
        "away_score": int(away.get("score") or 0),
        "scheduled_tipoff_utc": (comp.get("date") or "").replace(".000Z", "Z")
        if (comp.get("date") or "").endswith("Z") or "Z" in (comp.get("date") or "")
        else comp.get("date"),
        "status": "final" if status.get("completed") else status.get("name", "scheduled").lower(),
        "status_detail": status.get("description"),
    }


def normalize_tipoff(iso_value: str | None) -> str:
    if not iso_value:
        raise ValueError("missing tipoff")
    text = iso_value.strip()
    if text.endswith("Z"):
        return text.replace(".000Z", "Z")
    # ESPN sometimes returns offset form
    if "+" in text[10:] or text.count("-") > 2:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return text
