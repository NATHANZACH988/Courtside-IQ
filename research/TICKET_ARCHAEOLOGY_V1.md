# Ticket Archaeology — NBA, founding pass (2026-10-24)

**The question (Nate):** what did a ticket-builder actually *see* when they put a
ticket together — and which constructions win, which lose, and why? We rebuilt the
pre-tip information state for every banked final and graded the tickets that
state invites.

## Method (and its limits, stated up front)

- Universe: the agency's 28 banked finals, Oct 20–23. For each game, player
  profiles were rebuilt from **strictly earlier dates only** — no look-ahead.
- **Every leg in this pass rests on exactly one prior game per player.** The bank
  is two games deep per team, so this study measures the information state most
  early-season tickets are genuinely built in: one game of "evidence." Game-3+
  states begin tonight; the study re-runs as the bank deepens.
- No historical prop lines exist in our data. The proxy line is the player's own
  banked points/game floored to a book-style .5 line. This tests **selection**
  (who got picked, which direction), not price. Where a construction's premise is
  a mechanism rather than a number, we also grade it line-free (repeat rates).
- 14 games produced legs; 254 legs graded in total.

## Results by construction

| Construction | Legs | Leg win% | Tickets all-hit | What it is |
|---|---|---|---|---|
| PUBLIC_STAR overs | 52 | **28.8%** | 1/14 | Top-2 starters per team, over their banked average |
| ROLE_OVER (SGP filler) | 164 | 51.2% | **0/14** (0/14 at 4-leg cap too) | Starters 3–5 + rotation bench, overs |
| FOUL_FADE unders | 34 | 35.3% | 1/10 | Unders on players flagged for foul trouble |
| MECH_PAIRS | 4 | 50.0% | 0/2 | Cannibal over + victim under |
| ANTI (control) | 4 | 50.0% | 0/2 | The mirror image of MECH_PAIRS |

STEADY produced **zero legs** — not a bug: no clean high-usage starter had two
priors before any studied game. The construction can't even be tested until
tonight's game-3s bank.

## Why the losers lost (cause attribution)

- **PUBLIC_STAR (37 losses):** COLD/regression 21, game state 7, **foul cap 6**,
  minutes loss 3. The pattern is a winner's curse: the "top-2 by banked scoring"
  screen selects the players coming off their biggest night, then bets them to
  repeat it against a line anchored to that same night. Six of the losses weren't
  regression at all — the star got whistle-capped, a risk the public ticket never
  prices.
- **ROLE_OVER (80 losses):** COLD 39, minutes loss 16, game state 13, foul cap 10,
  cannibalized 2. The legs are individually fair (51.2%) — and the tickets still
  went 0-for-14. **Stacking fair legs is a losing construction by arithmetic,**
  independent of pick quality.
- **FOUL_FADE (22 losses):** role expansion 10, eruption 9. Line-free, the flag
  repeated terribly: of 34 flagged appearances, the player capped again only
  **2 times**, lost real minutes only 6 times. The trap: a capped game poisons
  the player's own average downward, so "under his average" is betting under a
  number the foul game itself suppressed. One whistle night is not a pattern.

## What repeated (line-free mechanism check)

- **Victim suppression: 2-for-2.** Both times a flagged victim started a later
  game, he scored under 60% of his banked average again. Tiny sample — and the
  only mechanism in the study that repeated at 100%.
- Cannibal repeat: 0-for-2 in this window (only two flagged bench players
  appeared in a later banked game). Unproven here, not disproven — tonight's
  frozen log carries 12 fresh cannibal calls, including two pairs that already
  fired on consecutive nights (Wiggins/McCollum, Ware/Turner).

## The one real ticket in our records

Nate's $50 FanDuel SGP, Oklahoma City @ San Antonio, Oct 20 — lost 2 of 4 legs.
The misses map one-to-one onto the mechanisms: **Cason Wallace (cannibalized** —
Jared McCain's bench surge took his attempts; Wallace finished with 6) and
**Isaiah Hartenstein (foul-capped** — 4th foul early in the third; finished with
4). The hits were the star over (Gilgeous-Alexander, 32) and a rebounds leg.
A ticket built by a sharp eye still died twice — both times to flow mechanisms
that were *visible in the data by halftime* and are now the model's frozen,
pre-tip predictions.

## Strategy rules this pass supports

1. **Never anchor an over to a one-game peak.** The public-star construction is
   the worst ticket in the study (28.8%) precisely because it buys yesterday's
   career night at yesterday's price.
2. **A single foul-cap game is not a fade.** Require the repeat — capped twice,
   or minutes suppression twice — before the foul mechanism earns a leg. Repeat
   offenders exist (Kyshawn George, capped in both his games); one-off whistle
   victims are the majority of flags and they bounce back.
3. **Ticket math beats leg quality.** ~51% legs swept 0 of 14 tickets. Any
   strategy chapter that talks about legs without talking about compounding is
   selling the product, not the edge.
4. **Bet mechanisms, not averages — and only mechanisms that have repeated.**
   Victim suppression is the founding example. The standard for promotion is the
   prediction log's: frozen pre-tip, graded after finals, no exceptions.
5. **The information state is a variable.** After one game, almost nothing
   repeats except regression. Constructions that look identical ("best players,
   over") flip from sucker bets to testable edges as the bank deepens — which is
   what the five-banker rule has been protecting all along.

## What happens next

Tonight's frozen 53 predictions are the first game-3 information state in the
bank. This study re-runs on a growing bank; the archetypes that matter
(MECH_PAIRS, STEADY) get their first real samples this week, and the win/loss
library becomes the strategy curriculum Nate asked for — built from what
actually happened to tickets, ours and the archetypes', wins and losses alike.

*Code: `pull/ticket_archaeology.py` · Data: `data/ticket_study.json` (agency repo).*
