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
import re
import hashlib
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

# A date-only check is insufficient: a same-day freeze can happen after tip.
# Neither these clock checks nor SHA digests independently attest source capture.
_REVISION = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_DATE = re.compile(r"^\\d{4}-\\d{2}-\\d{2}$")


def _valid_date(value):
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise SystemExit("date must be YYYY-MM-DD")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit("date must be a valid YYYY-MM-DD") from exc
    if parsed.strftime("%Y-%m-%d") != value:
        raise SystemExit("date must be YYYY-MM-DD")


def _utc_timestamp(value, label):
    if not isinstance(value, str):
        raise SystemExit(f"{label} must be an offset-aware timestamp")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise SystemExit(f"{label} is not a valid timestamp") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise SystemExit(f"{label} must include a timezone")
    return stamp.astimezone(timezone.utc)


def _require_pretip(games, at):
    if not isinstance(games, list) or not games:
        raise SystemExit("refusing to freeze an empty or invalid game slate")
    for game in games:
        if not isinstance(game, dict) or not game.get("event_id"):
            raise SystemExit("game schedule missing event ID")
        tip = _utc_timestamp(game.get("tip_utc"), "scheduled tip")
        if at >= tip:
            raise SystemExit(
                f"refusing post-tip freeze for event {game['event_id']}: "
                f"capture time {at.isoformat()} >= tip {tip.isoformat()}"
            )


def _verify_original_freeze(doc):
    """Fail closed on edited/post-tip input before any grade output is created.

    This is a structural guard, not proof the claimed freeze occurred.
    """
    if not isinstance(doc, dict) or doc.get("frozen") is not True:
        raise SystemExit("grading requires a frozen prediction manifest")
    built = _utc_timestamp(doc.get("built_at_utc"), "build timestamp")
    entries = doc.get("predictions")
    if not isinstance(entries, list) or not entries:
        raise SystemExit("grading requires nonempty frozen predictions")
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SystemExit(f"prediction {index} is not an object")
        tip = _utc_timestamp(entry.get("tip_utc"), f"prediction {index} tip")
        logged = _utc_timestamp(entry.get("logged_at_utc"),
                                f"prediction {index} logged")
        if built >= tip or logged >= tip or logged > built:
            raise SystemExit(f"prediction {index} was not frozen before tip")
        if entry.get("grade") is not None:
            raise SystemExit(f"prediction {index} already contains a grade")


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
    _valid_date(args.date)
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    if args.date < today:
        raise SystemExit(f"refusing to build for past date {args.date} (look-ahead)")
    os.makedirs(PRED_DIR, exist_ok=True)
    out = os.path.join(PRED_DIR, f"predictions-{args.date}.json")
    if os.path.exists(out):
        raise SystemExit(f"{out} already exists — the log is frozen once written")
    with open(BOARD, "rb") as source:
        board_bytes = source.read()
    board = json.loads(board_bytes)
    board_sha256 = hashlib.sha256(board_bytes).hexdigest()
    by_team = {}
    for r in board["players"]:
        by_team.setdefault(r["team"], []).append(r)
    games = fetch_board_games(args.date)
    frozen_at = datetime.now(timezone.utc)
    _require_pretip(games, frozen_at)
    entries = []
    now = frozen_at.isoformat()
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
           "board_sha256": board_sha256,
           "schedule_projection_sha256": hashlib.sha256(
               json.dumps(games, sort_keys=True).encode("utf-8")).hexdigest(),
           "finals_banked_at_build": board["finals_used"],
           "games": len(games), "predictions": entries}
    # Check again immediately before writing: a slow slate build must not
    # pass the first gate then publish after an event has started.
    _require_pretip(games, datetime.now(timezone.utc))
    try:
        with open(out, "x", encoding="utf-8") as target:
            json.dump(doc, target, indent=1)
    except FileExistsError as exc:
        raise SystemExit(f"{out} already exists — frozen logs are immutable") from exc
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
    _valid_date(args.date)
    src = os.path.join(PRED_DIR, f"predictions-{args.date}.json")
    with open(src, encoding="utf-8") as source:
        doc = json.load(source)
    _verify_original_freeze(doc)
    revision = getattr(args, "revision", None)
    reason = getattr(args, "reason", None)
    if revision is not None and (not isinstance(revision, str)
                                 or not _REVISION.fullmatch(revision)):
        raise SystemExit("revision must be a lowercase safe ID (max 40 chars)")
    if revision is None and reason is not None:
        raise SystemExit("--reason requires --revision")
    if revision is not None and (
            not isinstance(reason, str) or not reason.strip()):
        raise SystemExit("--revision requires a nonblank --reason")
    initial_out = os.path.join(PRED_DIR, f"predictions-{args.date}-graded.json")
    if revision is not None:
        if not os.path.isfile(initial_out):
            raise SystemExit("a later revision requires the original graded file")
        with open(initial_out, "rb") as prior:
            prior_sha256 = hashlib.sha256(prior.read()).hexdigest()
        out = os.path.join(PRED_DIR,
                           f"predictions-{args.date}-graded-{revision}.json")
    else:
        out = initial_out
        prior_sha256 = None
    if os.path.exists(out):
        raise SystemExit(f"{out} already exists — grade snapshots are immutable")
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
    graded = {**doc, "graded_at_utc": datetime.now(timezone.utc).isoformat(),
              "grade_revision": revision or "original",
              "grade_revision_reason": reason,
              "original_grade_sha256": prior_sha256,
              "predictions": results}
    try:
        with open(out, "x", encoding="utf-8") as target:
            json.dump(graded, target, indent=1)
    except FileExistsError as exc:
        raise SystemExit(f"{out} already exists — grade snapshots are immutable") from exc
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
        if name == "grade":
            p.add_argument("--revision", help="safe ID for a later immutable grade")
            p.add_argument("--reason", help="required reason for later grade revision")
    args = ap.parse_args()
    {"build": cmd_build, "grade": cmd_grade}[args.cmd](args)
