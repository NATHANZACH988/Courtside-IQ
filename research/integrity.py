"""Point-in-time provenance gates for captured NBA results.

These checks reject obviously inconsistent snapshots. They do NOT prove that a
source is authoritative, that a result is official, or that predictions were
recorded before tipoff. Those require separate evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse


def utc_timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def validate_completed_capture(fixture: dict) -> None:
    """Reject incomplete or temporally impossible 'final' box-score captures."""
    if str(fixture.get("status", "")).lower() != "final":
        raise ValueError("Completed-game capture requires status=final")

    tip = utc_timestamp(fixture.get("scheduled_tipoff_utc"), "scheduled_tipoff_utc")
    fetched = utc_timestamp(fixture.get("fetched_at_utc"), "fetched_at_utc")
    if fetched <= tip:
        raise ValueError("Final box score cannot be fetched at/before scheduled tipoff")

    source = fixture.get("source_url")
    if not isinstance(source, str) or urlparse(source).scheme != "https" or not urlparse(source).netloc:
        raise ValueError("source_url must be an HTTPS URL")

    if not fixture.get("game_id") or not fixture.get("home_team_id") or not fixture.get("away_team_id"):
        raise ValueError("Capture missing game or team identifiers")

    players = fixture.get("players")
    if not isinstance(players, list) or not players:
        raise ValueError("Completed-game capture requires nonempty players")
    for player in players:
        if not isinstance(player, dict) or not player.get("player_id"):
            raise ValueError("Each player must have a player_id")
