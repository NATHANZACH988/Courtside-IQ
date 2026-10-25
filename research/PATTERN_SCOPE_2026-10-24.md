# Pattern scope — NBA rotation seams, scoped (Oct 24, 2026, evening)

**Ledger:** pattern_notes.jsonl deduped by (event, type, player) — **55 foul caps,
33 bench surges** across 29 finals (Oct 20–24, incl. tonight's early filings);
115 player-events spread over **93 players**. Tool: `pull/pattern_scope.py` v2.
(v1 counted notes visible in final box snapshots and undercounted badly — a cap
that matures into 35 minutes vanishes from the final box. Superseded.)

## Corrections to this morning's pattern claims

- **Concentration was overstated.** Top 10 names hold only 24 of 115 events (21%).
  Leaders: Kel'el Ware, Myles Turner, Tre Johnson, GG Jackson — 3 events each.
  The seam action is league-wide texture, not a few names.
- **"Runs cluster late" was wrong.** 10+ unanswered-run starts by period:
  Q1 13, Q2 14, Q3 13, **Q4 6** — the fourth has the *fewest* starts
  (endgame fouling/timeouts break streaks). The Detroit 23-run was one event.
- **"Victim suppression repeated 100%" was a 2-case mirage.** With the full
  denominator — victims with a later banked game, ≥15 min — next-game
  suppression (<60% of banked ppg) is **2/8 (25%)**. Being eaten once does not,
  by itself, predict being eaten next game.

## What survives scoping

- **Usage theft is stickier than foul trouble.** Same-player repeat rates among
  players with a later banked game: CANNIBAL **3/13 (23%)**, VICTIM **3/13 (23%)**,
  CAP **1/31 (3%)**. Whistle events are near-random per player; rotation seams
  repeat at ~7× the rate. Kyshawn George (capped 2/2) is the lone cap repeater —
  an exception with n=2, not a class.
- **Team seams exist but don't dominate.** Milwaukee (3 cannibals / 3 victims /
  5 caps), Washington, Dallas, Memphis lead event volume; no team is an outlier
  factory. Oklahoma City — the vivid Wallace story — totals 5 events.
- **Tonight's frozen 53 are the arbiter.** The VICTIM mechanism (10 calls) is
  exactly the one whose persistence is unproven at 2/8; the FOUL_CAP mechanism
  (30 calls) rests on the least repeatable event in the bank. Expect the grading
  to be unkind to both and kinder to CANNIBAL (12 calls) — the process verdict
  lands with the finals.
