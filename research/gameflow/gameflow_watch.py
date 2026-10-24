"""Game-flow watcher: learns every game play-by-play, quietly.

For every NBA/NFL game on today's ESPN board (live or final), pulls the game
summary and extracts the flow features the pattern library cares about:
segment (quarter) scoring, unanswered runs, usage cannibalization (a bench
player out-attempting a starter), foul-trouble caps, star early exits.
Writes one JSON per game under data/gameflow/<league>/<date>/ and appends
notable patterns to data/gameflow/pattern_notes.jsonl. Silent by design:
stdout is a one-line count; remarkable events are flagged in the notes file
with "remarkable": true for the scheduler to surface.

Usage: venv/bin/python pull/gameflow_watch.py [nba|nfl|all]
"""
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

BASE = Path("/home/hatch/workspace/sports-analytics-agency")
OUT = BASE / "data" / "gameflow"
API = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/{ep}"

def fetch(sport, league, ep, **kw):
    url = API.format(sport=sport, league=league, ep=ep)
    if kw:
        url += "?" + "&".join(f"{k}={v}" for k, v in kw.items())
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())

def parse_fga(fg):
    try:
        m, a = fg.split("-")
        return int(m), int(a)
    except Exception:
        return 0, 0

def nba_game(eid):
    d = fetch("basketball", "nba", "summary", event=eid)
    comp = d["header"]["competitions"][0]
    status = comp["status"]["type"]["description"]
    teams = {c["team"]["abbreviation"]: int(c["score"] or 0) for c in comp["competitors"]}
    seg = {}
    for c in comp["competitors"]:
        seg[c["team"]["abbreviation"]] = [int(x.get("displayValue") or x.get("value") or 0) for x in c.get("linescores", [])]
    plays = d.get("plays", [])
    # unanswered runs >= 10 by segment start
    runs, notes = [], []
    cur_team, cur_pts, cur_per = None, 0, None
    last = {"home": 0, "away": 0}
    home_ab = [a for a, c in zip(teams, comp["competitors"]) if c["homeAway"] == "home"][0]
    score_now = {a: 0 for a in teams}
    prev_total = {a: 0 for a in teams}
    streak = {"team": None, "pts": 0, "start_period": None}
    for p in plays:
        txt = p.get("text", "")
        sc = p.get("scoreValue", 0) or 0
        t = p.get("team", {}).get("id")
        if sc > 0 and p.get("scoringPlay"):
            ab = None
            for c in comp["competitors"]:
                if c["team"]["id"] == t:
                    ab = c["team"]["abbreviation"]
            if ab:
                if streak["team"] == ab:
                    streak["pts"] += sc
                else:
                    if streak["team"] and streak["pts"] >= 10:
                        runs.append(dict(streak))
                    streak = {"team": ab, "pts": sc, "start_period": p["period"]["number"]}
    if streak["team"] and streak["pts"] >= 10:
        runs.append(dict(streak))
    # player usage / fouls
    players = []
    for team in d.get("boxscore", {}).get("players", []):
        tab = team["team"]["abbreviation"]
        labels = team["statistics"][0]["labels"]
        for a in team["statistics"][0]["athletes"]:
            s = dict(zip(labels, a["stats"]))
            fgm, fga = parse_fga(s.get("FG", "0-0"))
            players.append({"name": a["athlete"]["displayName"], "team": tab,
                            "pos": (a["athlete"].get("position") or {}).get("abbreviation", ""),
                            "starter": bool(a.get("starter")), "min": s.get("MIN"),
                            "pts": int(s.get("PTS") or 0), "reb": int(s.get("REB") or 0),
                            "fga": fga, "fgm": fgm, "pf": int(s.get("PF") or 0)})
    by_team = defaultdict(list)
    for pl in players:
        by_team[pl["team"]].append(pl)
    def mins(p):
        try:
            return float(str(p["min"]).split(":")[0])
        except Exception:
            return 0.0
    _scores = list(teams.values())
    margin = abs(_scores[0] - _scores[1]) if len(_scores) == 2 else 0
    for tab, ps in by_team.items():
        for p in ps:
            pm = mins(p)
            if not p["starter"] and pm >= 8 and p["fga"] / pm >= 0.45 and p["pts"] >= 6 and margin < 20:
                same_pos_starters = [s for s in ps if s["starter"] and s["pos"] == p["pos"] and mins(s) >= 8 and s["fga"] >= 2]
                if same_pos_starters:
                    slot = min(same_pos_starters, key=lambda s: s["fga"] / mins(s))
                    if p["fga"] / pm >= 1.5 * (slot["fga"] / mins(slot)) and p["pts"] >= slot["pts"]:
                        notes.append({"type": "bench_usage_surge", "team": tab, "bench_player": p["name"],
                                      "pos": p["pos"], "fga_per_min": round(p["fga"] / pm, 2),
                                      "bench_pts": p["pts"], "min": p["min"],
                                      "slot_starter": slot["name"], "slot_pts": slot["pts"]})
            if p["pf"] >= 4:
                try:
                    if float(str(p["min"]).split(":")[0]) <= 20:
                        notes.append({"type": "foul_trouble_cap", "team": tab, "player": p["name"],
                                      "pf": p["pf"], "min": p["min"], "pts": p["pts"]})
                except Exception:
                    pass
    remarkable = [n for n in notes if n["type"] in ("bench_usage_surge",)] + \
                 [r for r in runs if r["pts"] >= 20]
    return {"league": "nba", "event": eid, "status": status, "teams": teams,
            "segment_scores": seg, "runs10": runs, "notes": notes,
            "remarkable": bool(remarkable), "players": players}

def nfl_game(eid):
    d = fetch("football", "nfl", "summary", event=eid)
    comp = d["header"]["competitions"][0]
    status = comp["status"]["type"]["description"]
    teams = {c["team"]["abbreviation"]: int(c["score"] or 0) for c in comp["competitors"]}
    seg = {}
    for c in comp["competitors"]:
        seg[c["team"]["abbreviation"]] = [int(x.get("displayValue") or x.get("value") or 0) for x in c.get("linescores", [])]
    notes = []
    for p in d.get("plays", []):
        t = p.get("text", "")
        if "enters the game" in t and ("QB" in t or "quarterback" in t.lower()):
            notes.append({"type": "qb_change_text", "text": t})
    return {"league": "nfl", "event": eid, "status": status, "teams": teams,
            "segment_scores": seg, "notes": notes, "remarkable": False}

def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    done = 0
    for league, sport, fn in [("nba", "basketball", nba_game), ("nfl", "football", nfl_game)]:
        if which not in ("all", league):
            continue
        try:
            board = fetch(sport, league, "scoreboard")
        except Exception as e:
            print(f"{league}: board fetch failed ({e})")
            continue
        day = (board.get("day") or {}).get("date", "unknown")
        outdir = OUT / league / str(day)
        outdir.mkdir(parents=True, exist_ok=True)
        for e in board.get("events", []):
            if (e.get("status", {}).get("type", {}) or {}).get("state") == "pre":
                continue  # not started: nothing to learn yet
            try:
                g = fn(e["id"])
            except Exception as ex:
                print(f"{league} {e['id']}: {ex}")
                continue
            (outdir / f"{e['id']}.json").write_text(json.dumps(g, indent=1))
            if g["notes"] or g.get("runs10"):
                with open(OUT / "pattern_notes.jsonl", "a") as f:
                    f.write(json.dumps({"league": league, "event": e["id"], "day": str(day),
                                        "status": g["status"], "runs": g.get("runs10", []),
                                        "notes": g["notes"], "remarkable": g["remarkable"]}) + "\n")
            done += 1
    print(f"gameflow: {done} games written")

if __name__ == "__main__":
    main()
