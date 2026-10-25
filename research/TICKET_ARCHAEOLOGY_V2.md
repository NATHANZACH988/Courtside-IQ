# Ticket Archaeology — v2 addendum (2026-10-24)

Second dig on the same bank (28 finals, one-prior information state, proxy
lines = banked averages; selection test, not price). Code:
`pull/ticket_archaeology_v2.py`, reproduces every number below.

## 1. The rebounds market is worse than the points market

| Construction | Legs | Win% |
|---|---|---|
| Top-2 starters by banked rebounds, over | 52 | 38.5% |
| Bench bigs (F/C, ≥4 reb/g), over | 31 | 35.5% |
| **Starting guards (≥5 reb/g), over** | 21 | **14.3%** |

Guard-rebound overs are the single worst construction measured in either pass —
3 wins in 21. Rebounds are opportunity stats: they belong to game state,
matchup, and whoever the opposing bigs drag out of position, none of which a
one-game average sees. Loss causes for big-man overs were mostly OUTPLAYED (23)
— plain glass variance — with fouls (2) and game state (7) behind.

The exception that proves the framing: the one rebound leg on Nate's real
parlay — Jalen Williams, 7 boards — *cashed*. Individuals beat variance;
constructions don't. A strategy is the construction, not the anecdote.

## 2. Ticket-shape decay: the product is the compounding

Sweep rate by number of legs in the ticket (all archetypes, 42 tickets):

| Legs | Tickets | Swept |
|---|---|---|
| 2 | 9 | 2 |
| 3 | 5 | 0 |
| 4 | 12 | 0 |
| 5 | 2 | 0 |
| 6+ | 14 | 0 |

Two sweeps in 42 tickets, both at 2 legs. Every ticket of 3+ legs in the study
died. This is not a picking failure distributed evenly — it is the shape of the
product. Any "strategy" content that celebrates leg quality while stacking 4–6
of them is describing the losing construction with better marketing.

## 3. The one-leg-away autopsy: "so close" is mostly a myth

Of 42 tickets, exactly **2** died by a single leg — and both were FOUL_FADE
tickets killed by the fade target erupting instead (Ziaire Williams scored 14
against a 9.5 under; Sidy Cissoko, a deep-bench name, scored 15 against a 3.5
under). Tickets in this bank did not die by one leg; they died by construction,
in bunches. The near-miss feeling is the product's retention feature, not a
property of the bets.

## 4. COLD, decomposed: did he get his shots?

The 61 losing overs previously filed as COLD split cleanly on pre-game state:

- **SHOTS MISSED — 44.** The player took at least 70% of his banked attempts
  and simply didn't convert (Gilgeous-Alexander: 19 attempts vs 27 banked,
  17 points). Against a line anchored to a one-game peak, this is the
  winner's-curse tax — a price problem, not a flow problem. No model fixes it;
  only refusing the anchor does.
- **SHOTS TAKEN AWAY — 17.** Attempts collapsed by 30%+ (Kentavious
  Caldwell-Pope: 1 attempt vs 8 banked; Jared McCain: 6 vs 9). This is flow —
  role, matchup, a teammate's eruption — and it is the slice of "cold" the
  game-flow model has jurisdiction over.

Grading rule that follows: every losing over gets asked one question first —
*did he get his shots?* Variance losses get filed to the price ledger; flow
losses get filed to the model. Mixing them is how both get misjudged.

## Updated strategy rules (additions to the founding five)

6. **There is no safe filler leg.** Guard rebounds — the classic "free" SGP
   add-on — are the worst leg in the bank at 14.3%. The correct filler is
   fewer legs.
7. **Sell the shape, not the story.** At these hit rates the only reliable
   edge in ticket construction is subtraction: 2-leg tickets swept 2 of 9;
   everything longer swept nothing.
8. **Autopsy before strategy.** Wins and losses both get cause-coded
   (foul / taken / missed / variance / eruption) before any rule is drawn
   from them. A win by variance teaches nothing; a loss by flow teaches
   everything.
