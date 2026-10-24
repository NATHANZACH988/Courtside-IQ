#!/usr/bin/env python3
"""Full-roster board (owner directive 2026-10-24): EVERY player who has
appeared in a banked final — starters and bench, no minute floor.
Thin samples are flagged, never excluded: the next eruption candidate
is exactly the player a threshold would hide.

Reads data/gameflow/nba/*/*.json finals, merges mechanism flags from
data/scoring_profiles.json, writes data/full_roster_board.json.
"""
import glob
import json
import os
from collections import Counter, defaultdict

ROOT = os.path.join(os.path.dirname(__file__), "..")
GF = os.path.join(ROOT, "data", "gameflow", "nba")
OUT = os.path.join(ROOT, "data", "full_roster_board.json")
PROFILES = os.path.join(ROOT, "data", "scoring_profiles.json")


def parse_min(v):
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if ":" in s:  # MM:SS
        m, sec = s.split(":", 1)
        return int(m) + int(sec) / 60.0
    try:
        return float(s)
    except ValueError:  # '--' and friends: did not play
        return 0.0


def main():
    agg = {}
    finals = 0
    for path in sorted(glob.glob(os.path.join(GF, "*", "*.json"))):
        d = json.load(open(path))
        if not str(d.get("status", "")).lower().startswith("final"):
            continue
        finals += 1
        for p in d.get("players", []):
            a = agg.setdefault(p["name"], {
                "name": p["name"], "teams": Counter(), "positions": Counter(),
                "games": 0, "dnp": 0, "starts": 0, "min": 0.0, "pts": 0, "fga": 0, "pf": 0})
            a["teams"][p.get("team", "?")] += 1
            if parse_min(p.get("min")) <= 0:  # rostered but did not play
                a["dnp"] += 1
                if p.get("pos"):
                    a["positions"][p["pos"]] += 1
                continue
            if p.get("pos"):
                a["positions"][p["pos"]] += 1
            a["games"] += 1
            a["starts"] += 1 if p.get("starter") else 0
            a["min"] += parse_min(p.get("min"))
            a["pts"] += p.get("pts", 0) or 0
            a["fga"] += p.get("fga", 0) or 0
            a["pf"] += p.get("pf", 0) or 0

    flags = {}
    if os.path.exists(PROFILES):
        prof = json.load(open(PROFILES)).get("players", {})
        for name, pr in prof.items():
            flags[name] = {
                "capped_events": pr.get("capped_events", 0),
                "cannibal_events": pr.get("cannibal_events", 0),
                "victim_events": pr.get("victim_events", 0),
            }

    board = []
    for name, a in agg.items():
        g, mins = a["games"], a["min"]
        gd = max(g, 1)
        board.append({
            "name": name,
            "team": a["teams"].most_common(1)[0][0],
            "position": a["positions"].most_common(1)[0][0] if a["positions"] else None,
            "games": g,
            "dnp": a["dnp"],
            "starts": a["starts"],
            "bench_games": g - a["starts"],
            "min_pg": round(mins / gd, 1),
            "total_min": round(mins, 1),
            "pts_pg": round(a["pts"] / gd, 1),
            "fga_per_min": round(a["fga"] / mins, 2) if mins else 0.0,
            "pf_per36": round(a["pf"] * 36 / mins, 1) if mins else 0.0,
            "thin_sample": g < 2 or mins < 30,
            **flags.get(name, {"capped_events": 0, "cannibal_events": 0, "victim_events": 0}),
        })
    board.sort(key=lambda r: (r["team"], -r["pts_pg"]))
    json.dump({"finals_used": finals, "players": board}, open(OUT, "w"), indent=1)
    thin = sum(1 for r in board if r["thin_sample"])
    print(f"finals: {finals}; players on board: {len(board)} "
          f"(thin-sample flagged, not excluded: {thin})")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
