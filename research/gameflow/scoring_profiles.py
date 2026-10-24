"""Scoring-likelihood profiles from banked game-flow data.

Turns the watcher's per-game files into per-player evidence on WHO SCORES
and who gets shut off, via the mechanisms discovered live (Oct 20-22):
  - foul_trouble_cap events (player's minutes/scoring capped by fouls)
  - bench usage surges (the 'cannibal' who eats a starter's attempts)
  - surge victims (the slot starter whose usage was taken)
  - foul rate (PF per 36) and usage rate (FGA/min) from final box scores

EVIDENCE ONLY under agency governance: no pick authority. Prospective
predictions get logged separately and graded before any promotion.

Usage: venv/bin/python pull/scoring_profiles.py
Output: data/scoring_profiles.json + a printed board.
"""
import json
from collections import defaultdict
from pathlib import Path

BASE = Path("/home/hatch/workspace/sports-analytics-agency")
GF = BASE / "data" / "gameflow" / "nba"
NOTES = BASE / "data" / "gameflow" / "pattern_notes.jsonl"
OUT = BASE / "data" / "scoring_profiles.json"

def mins(v):
    try:
        return float(str(v).split(":")[0])
    except Exception:
        return 0.0

def main():
    players = defaultdict(lambda: {"games": 0, "starts": 0, "min": 0.0, "pts": 0,
                                   "fga": 0, "pf": 0, "teams": set(),
                                   "capped": 0, "cannibal": 0, "victim": 0,
                                   "low_games": 0})
    games_used, games_skipped = 0, 0
    seen_events = set()
    for f in sorted(GF.glob("*/*.json")):
        g = json.loads(f.read_text())
        if g.get("status") != "Final":
            games_skipped += 1
            continue
        games_used += 1
        ckey = (g["event"], "cap")
        for p in g.get("players", []):
            d = players[p["name"]]
            d["games"] += 1
            d["starts"] += 1 if p["starter"] else 0
            d["min"] += mins(p["min"])
            d["pts"] += p["pts"]
            d["fga"] += p["fga"]
            d["pf"] += p["pf"]
            d["teams"].add(p["team"])
    # deduped pattern events (notes file repeats per watcher run)
    if NOTES.exists():
        for line in NOTES.read_text().splitlines():
            try:
                n = json.loads(line)
            except Exception:
                continue
            if n.get("league") != "nba":
                continue
            for note in n.get("notes", []):
                if note["type"] == "foul_trouble_cap":
                    k = (n["event"], "cap", note["player"])
                    if k not in seen_events:
                        seen_events.add(k)
                        players[note["player"]]["capped"] += 1
                elif note["type"] == "bench_usage_surge":
                    k = (n["event"], "surge", note["bench_player"])
                    if k not in seen_events:
                        seen_events.add(k)
                        players[note["bench_player"]]["cannibal"] += 1
                        if note.get("slot_starter"):
                            players[note["slot_starter"]]["victim"] += 1
    board = {}
    for name, d in players.items():
        if d["games"] == 0 or d["min"] < 20:
            continue
        pf36 = 36 * d["pf"] / d["min"] if d["min"] else 0
        board[name] = {
            "team": sorted(d["teams"]), "games": d["games"], "starts": d["starts"],
            "min_pg": round(d["min"] / d["games"], 1), "pts_pg": round(d["pts"] / d["games"], 1),
            "fga_per_min": round(d["fga"] / d["min"], 2) if d["min"] else 0,
            "pf_per36": round(pf36, 1),
            "capped_events": d["capped"], "cannibal_events": d["cannibal"],
            "victim_events": d["victim"],
            "foul_risk": pf36 >= 4.8,
        }
    OUT.write_text(json.dumps({"games_used": games_used, "games_skipped_nonfinal": games_skipped,
                               "players": board}, indent=1))
    print(f"final games used: {games_used} (skipped non-final snapshots: {games_skipped}); players profiled: {len(board)}")
    def show(title, rows, fmt):
        print(f"\n== {title} ==")
        for name, b in rows:
            print(" ", fmt(name, b))
    foul = sorted([(n, b) for n, b in board.items() if b["foul_risk"] or b["capped_events"]],
                  key=lambda x: (-x[1]["capped_events"], -x[1]["pf_per36"]))[:10]
    show("WON'T-SCORE RISK: foul trouble (capped events, PF/36)", foul,
         lambda n, b: f"{n} ({'/'.join(b['team'])}) — capped {b['capped_events']}x, {b['pf_per36']} PF/36, {b['pts_pg']} pts/g")
    cann = sorted([(n, b) for n, b in board.items() if b["cannibal_events"]],
                  key=lambda x: -x[1]["cannibal_events"])[:10]
    show("WILL-SCORE (off the bench): usage cannibals", cann,
         lambda n, b: f"{n} ({'/'.join(b['team'])}) — surged {b['cannibal_events']}x, {b['pts_pg']} pts/g, {b['fga_per_min']} FGA/min")
    vic = sorted([(n, b) for n, b in board.items() if b["victim_events"]],
                 key=lambda x: -x[1]["victim_events"])[:10]
    show("WON'T-SCORE RISK: usage victims (starter slot taken by bench)", vic,
         lambda n, b: f"{n} ({'/'.join(b['team'])}) — victim {b['victim_events']}x, {b['pts_pg']} pts/g in {b['min_pg']} min/g")
    steady = sorted([(n, b) for n, b in board.items() if b["starts"] >= 2 and b["min_pg"] >= 24],
                    key=lambda x: -x[1]["fga_per_min"])[:10]
    show("WILL-SCORE: steadiest starter usage (FGA/min, 2+ starts, 24+ min/g)", steady,
         lambda n, b: f"{n} ({'/'.join(b['team'])}) — {b['fga_per_min']} FGA/min, {b['pts_pg']} pts/g, {b['pf_per36']} PF/36")

if __name__ == "__main__":
    main()
