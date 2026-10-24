#!/usr/bin/env python3
"""Prospective prediction log (owner directive 2026-10-24).

The model PREDICTS the patterns the watcher has been detecting: before
tip, for every game on the board, named predictions (player + mechanism
+ direction) are written from the full-roster board and FROZEN. After
finals, `grade` scores them against the actual gameflow files. The
original log is never edited; grades land in a sibling file.

Usage:
  prediction_log.py build --date YYYY-MM-DD   (today/future only)
  prediction_log.py grade --date YYYY-MM-DD

Mechanisms:
  FOUL_CAP  DOWN  capped before, or PF/36 >= 5.5 -> scoring suppressed
  CANNIBAL  UP    bench player with a prior surge -> erupts again
  VICTIM    DOWN  starter whose slot was taken before -> suppressed again
  STEADY    UP    clean high-usage starter -> scores at his banked level

Grading rules (deterministic, from the final's gameflow file):
  FOUL_CAP  HIT if a foul-trouble-cap note names the player, or PF >= 5,
            or PF == 4 in <= 65% of his banked minutes/game.
  CANNIBAL  HIT if the hardened-detector shape recurs: bench, >= 8 min,
            FGA/min >= 0.45, >= 1.5x a same-position starter's rate
            (starter >= 2 FGA), points >= that starter's, margin < 20.
  VICTIM    HIT if points < 60% of banked PPG in >= 15 min, or a
            same-position bench teammate posts the cannibal shape on him.
  STEADY    HIT if points >= banked PPG - 3 in >= 15 min.
  Any: minutes < 10 -> NO_DECISION (he barely played; no evidence).
"""
import argparse
import glob
import json
import os
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.join(os.path.dirname(__file__), "..")
BOARD = os.path.join(ROOT, "data", "full_roster_board.json")
PRED_DIR = os.path.join(ROOT, "data", "predictions")
GF = os.path.join(ROOT, "data", "gameflow", "nba")
UA = {"User-Agent": "Mozilla/5.0"}

# Victim evidence for Gafford is contaminated: 2 of his flags are the
# retracted pre-hardening DAL false positives (2026-10-21). Excluded
# from predictions until clean games wash the count out.
EXCLUSIONS = {"Daniel Gafford": "victim flags contaminated by retracted detector artifacts"}


def pmin(v):
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if ":" in s:
        m, sec = s.split(":", 1)
        return int(m) + int(sec) / 60.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def fetch_board_games(date):
    url = ("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/"
           f"scoreboard?dates={date.replace('-', '')}")
    req = urllib.request.Request(url, headers=UA)
    d = json.load(urllib.request.urlopen(req, timeout=30))
    games = []
    for e in d.get("events", []):
        comp = e["competitions"][0]
        abbr = {t["homeAway"]: t["team"]["abbreviation"] for t in comp["competitors"]}
        games.append({"event_id": e["id"], "tip_utc": e["date"],
                      "home": abbr.get("home"), "away": abbr.get("away")})
    return games


def predictions_for(r, opp):
    """Yield (mechanism, direction, basis) for one board row."""
    banked = (f"{r['games']}g, {r['pts_pg']} pts/g, {r['fga_per_min']} FGA/min, "
              f"{r['pf_per36']} PF/36, capped {r['capped_events']}x, "
              f"cannibal {r['cannibal_events']}x, victim {r['victim_events']}x")
    starter_majority = r["starts"] >= r["bench_games"] and r["starts"] >= 1
    bench_majority = r["bench_games"] > r["starts"]
    if r["games"] >= 1 and r["total_min"] >= 20 and (
            r["capped_events"] >= 1 or r["pf_per36"] >= 5.5):
        yield ("FOUL_CAP", "DOWN",
               f"foul suppression risk vs {opp}: {banked}")
    if bench_majority and r["cannibal_events"] >= 1:
        yield ("CANNIBAL", "UP",
               f"prior bench surge(s) vs field; eruption risk vs {opp}: {banked}")
    if starter_majority and r["victim_events"] >= 1 and r["name"] not in EXCLUSIONS:
        yield ("VICTIM", "DOWN",
               f"slot usage taken by bench before; suppression risk vs {opp}: {banked}")
    if (starter_majority and r["games"] >= 2 and r["fga_per_min"] >= 0.50
            and r["pf_per36"] <= 2.5 and r["capped_events"] == 0
            and r["victim_events"] == 0):
        yield ("STEADY", "UP",
               f"clean high-usage starter; holds his level vs {opp}: {banked}")


def cmd_build(args):
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    if args.date < today:
        raise SystemExit(f"refusing to build for past date {args.date} (look-ahead)")
    os.makedirs(PRED_DIR, exist_ok=True)
    out = os.path.join(PRED_DIR, f"predictions-{args.date}.json")
    if os.path.exists(out):
        raise SystemExit(f"{out} already exists — the log is frozen once written")
    board = json.load(open(BOARD))
    by_team = {}
    for r in board["players"]:
        by_team.setdefault(r["team"], []).append(r)
    games = fetch_board_games(args.date)
    entries = []
    now = datetime.now(timezone.utc).isoformat()
    for g in games:
        for side, opp_side in (("home", "away"), ("away", "home")):
            team, opp = g[side], g[opp_side]
            for r in by_team.get(team, []):
                if r["games"] == 0:
                    continue  # rostered, never played: on the board, no evidence yet
                for mech, direction, basis in predictions_for(r, opp):
                    entries.append({
                        "player": r["name"], "team": team, "opponent": opp,
                        "event_id": g["event_id"], "tip_utc": g["tip_utc"],
                        "mechanism": mech, "direction": direction,
                        "banked_pts_pg": r["pts_pg"], "banked_min_pg": r["min_pg"],
                        "thin_sample": r["thin_sample"],
                        "basis": basis, "logged_at_utc": now, "grade": None})
    doc = {"date": args.date, "built_at_utc": now, "frozen": True,
           "finals_banked_at_build": board["finals_used"],
           "games": len(games), "predictions": entries}
    json.dump(doc, open(out, "w"), indent=1)
    from collections import Counter
    print(f"games: {len(games)}; predictions frozen: {len(entries)}")
    print(Counter(e["mechanism"] for e in entries))
    print(f"wrote {out}")


def load_final(event_id):
    for path in glob.glob(os.path.join(GF, "*", f"{event_id}.json")):
        d = json.load(open(path))
        if str(d.get("status", "")).lower().startswith("final"):
            return d
    return None


def cannibal_shape(players, name):
    """Hardened-detector shape for `name` within one final's player list."""
    me = next((p for p in players if p["name"] == name), None)
    if not me or me.get("starter"):
        return False
    mins = pmin(me.get("min"))
    if mins < 8 or not me.get("fga"):
        return False
    my_rate = me["fga"] / mins
    if my_rate < 0.45:
        return False
    for s in players:
        if (s.get("starter") and s["team"] == me["team"]
                and s.get("pos") == me.get("pos") and (s.get("fga") or 0) >= 2):
            s_mins = pmin(s.get("min"))
            if s_mins and my_rate >= 1.5 * (s["fga"] / s_mins) \
                    and (me.get("pts") or 0) >= (s.get("pts") or 0):
                return True
    return False


def grade_entry(e, final):
    players = final.get("players", [])
    me = next((p for p in players if p["name"] == e["player"]), None)
    if me is None:
        return "NO_DECISION", "not in box score"
    mins = pmin(me.get("min"))
    pts = me.get("pts") or 0
    pf = me.get("pf") or 0
    if mins < 10:
        return "NO_DECISION", f"only {mins:.0f} min played"
    mech = e["mechanism"]
    if mech == "FOUL_CAP":
        noted = any(n.get("player") == e["player"]
                    and "foul" in str(n.get("type", ""))
                    for n in final.get("notes", []))
        if noted or pf >= 5 or (pf == 4 and mins <= 0.65 * e["banked_min_pg"]):
            return "HIT", f"{pf} PF in {mins:.0f} min"
        return "MISS", f"{pf} PF in {mins:.0f} min, scored {pts}"
    if mech == "CANNIBAL":
        seg = final.get("segments", [])
        margin = None
        if seg:
            margin = abs(sum(s.get("home", 0) - s.get("away", 0) for s in seg)) \
                if isinstance(seg[0], dict) else None
        if margin is not None and margin >= 20:
            return "NO_DECISION", f"blowout margin {margin}"
        return ("HIT", "surge shape recurred") if cannibal_shape(players, e["player"]) \
            else ("MISS", f"{pts} pts in {mins:.0f} min, no surge shape")
    if mech == "VICTIM":
        if cannibal_shape_on(players, e["player"]):
            return "HIT", "bench teammate posted the cannibal shape on his slot"
        if mins >= 15 and pts < 0.6 * e["banked_pts_pg"]:
            return "HIT", f"{pts} pts vs {e['banked_pts_pg']} banked"
        return "MISS", f"{pts} pts in {mins:.0f} min"
    if mech == "STEADY":
        if pts >= e["banked_pts_pg"] - 3:
            return "HIT", f"{pts} pts vs {e['banked_pts_pg']} banked"
        return "MISS", f"{pts} pts vs {e['banked_pts_pg']} banked"
    return "NO_DECISION", "unknown mechanism"


def cannibal_shape_on(players, starter_name):
    st = next((p for p in players if p["name"] == starter_name), None)
    if not st or not st.get("starter"):
        return False
    return any(cannibal_shape(players, p["name"]) and p["team"] == st["team"]
               and p.get("pos") == st.get("pos")
               for p in players if not p.get("starter"))


def cmd_grade(args):
    src = os.path.join(PRED_DIR, f"predictions-{args.date}.json")
    doc = json.load(open(src))
    finals = {}
    results, pending = [], 0
    for e in doc["predictions"]:
        if e["event_id"] not in finals:
            finals[e["event_id"]] = load_final(e["event_id"])
        fin = finals[e["event_id"]]
        if fin is None:
            pending += 1
            results.append({**e, "grade": "PENDING", "grade_note": "game not final"})
            continue
        grade, note = grade_entry(e, fin)
        results.append({**e, "grade": grade, "grade_note": note})
    out = os.path.join(PRED_DIR, f"predictions-{args.date}-graded.json")
    json.dump({**doc, "graded_at_utc": datetime.now(timezone.utc).isoformat(),
               "predictions": results}, open(out, "w"), indent=1)
    from collections import Counter
    print("by mechanism:")
    by = {}
    for r in results:
        by.setdefault(r["mechanism"], Counter())[r["grade"]] += 1
    for m, c in sorted(by.items()):
        print(f"  {m}: {dict(c)}")
    print(f"pending (not final): {pending}; wrote {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build", "grade"):
        p = sub.add_parser(name)
        p.add_argument("--date", required=True)
    args = ap.parse_args()
    {"build": cmd_build, "grade": cmd_grade}[args.cmd](args)
