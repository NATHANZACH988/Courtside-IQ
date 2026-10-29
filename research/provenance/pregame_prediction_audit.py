"""Offline, research-only chronology audit for prospective NBA mechanism logs.

Validates claims within a frozen file; cannot authenticate source data,
independently attest creation time, or certify the pregame bank cutoff.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path

MECHANISMS = {"FOUL_CAP": "DOWN", "CANNIBAL": "UP", "VICTIM": "DOWN", "STEADY": "UP"}


def _timestamp(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label}: timestamp string required")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label}: invalid timestamp") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError(f"{label}: timezone required")
    return stamp


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: nonempty string required")
    return value


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{label}: finite nonnegative number required")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"nonstandard JSON number: {value}")


def audit(doc):
    """Raise ValueError on inconsistent self-declared freeze evidence.

    This is *not* independent proof that a file existed before tipoff.
    """
    if not isinstance(doc, dict) or doc.get("frozen") is not True:
        raise ValueError("frozen prediction document required")
    built = _timestamp(doc.get("built_at_utc"), "built_at_utc")
    banked = doc.get("finals_banked_at_build")
    if type(banked) is not int or banked < 0:
        raise ValueError("finals_banked_at_build: nonnegative integer required")
    entries = doc.get("predictions")
    if not isinstance(entries, list):
        raise ValueError("predictions: list required")
    seen = set()
    events = {}
    for i, entry in enumerate(entries):
        label = f"predictions[{i}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{label}: object required")
        event_id = _text(entry.get("event_id"), f"{label}.event_id")
        player = _text(entry.get("player"), f"{label}.player")
        team = _text(entry.get("team"), f"{label}.team")
        opp = _text(entry.get("opponent"), f"{label}.opponent")
        if team == opp:
            raise ValueError(f"{label}: team cannot play itself")
        mechanism = entry.get("mechanism")
        if mechanism not in MECHANISMS or entry.get("direction") != MECHANISMS[mechanism]:
            raise ValueError(f"{label}: invalid mechanism/direction")
        if entry.get("grade") is not None:
            raise ValueError(f"{label}: frozen pregame grade must be null")
        if type(entry.get("thin_sample")) is not bool:
            raise ValueError(f"{label}: thin_sample must be boolean")
        _number(entry.get("banked_pts_pg"), f"{label}.banked_pts_pg")
        _number(entry.get("banked_min_pg"), f"{label}.banked_min_pg")
        tip = _timestamp(entry.get("tip_utc"), f"{label}.tip_utc")
        logged = _timestamp(entry.get("logged_at_utc"), f"{label}.logged_at_utc")
        if not built <= logged < tip:
            raise ValueError(f"{label}: build/logged timestamp not before tip")
        ident = (event_id, team, player, mechanism)
        if ident in seen:
            raise ValueError(f"{label}: duplicate player-mechanism event")
        seen.add(ident)
        if event_id in events:
            prior_tip, teams = events[event_id]
            if tip != prior_tip or frozenset((team, opp)) != teams:
                raise ValueError(f"{label}: event tip or teams conflict")
        else:
            events[event_id] = (tip, frozenset((team, opp)))
    return {"entries": len(entries), "events_with_predictions": len(events),
            "chronology_claims_consistent": True,
            "independent_timestamp_verified": False,
            "pregame_bank_cutoff_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    doc = json.loads(args.file.read_text(encoding="utf-8"),
                     object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    print(json.dumps(audit(doc), indent=2))


if __name__ == "__main__":
    main()
