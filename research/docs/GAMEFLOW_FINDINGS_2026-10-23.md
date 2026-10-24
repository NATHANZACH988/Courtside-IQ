# Game-flow findings — measured, 2026-10-20 → 2026-10-23

**Source:** live play-by-play watcher (`research/gameflow/gameflow_watch.py`)
over the ESPN summary feed, running every 15 minutes since 2026-10-20.
**Coverage at this pull (2026-10-23 ~20:57 ET):** 17 NBA finals banked,
206 players profiled. **Labels:** everything below is an *observed fact* about
completed games unless marked *hypothesis*. Predictive value is unproven;
promotion requires the prospective grading path in AGENCY_BRIDGE.md.

## Finding 1 — Foul trouble caps scoring before it caps minutes

31 deduped foul-cap events (4 personal fouls in ≤20 minutes played) across
17 finals — roughly 1.8 per game. A capped player's scoring line is usually
already decided when the 4th foul lands.

- Repeat offender: **Kyshawn George (WSH)** — capped twice in three nights.
- Highest foul rates among capped players (PF/36): Brayden Burries 10.5,
  Noah Clowney 9.8, Ousmane Dieng 8.8, Kel'el Ware 8.7.
- Exemplar (the founding observation, 2026-10-20, OKC @ SA): Isaiah
  Hartenstein picked up his 4th foul 90 seconds into the 3rd quarter, sat,
  and finished with 4 points against a 5-point expectation. His banked
  profile since: 6.3 PF/36, 5.0 pts/g.

## Finding 2 — Bench usage surges take a specific starter's attempts

18 deduped bench-usage-surge events (detector spec in DETECTOR_SPEC.md).
The pattern is positional and personal: one bench player, one slot starter.

- Repeat cannibals: **Aaron Wiggins (ATL) 2×**, **Kel'el Ware (MIL) 2×**.
- Repeat pair: Ware over **Myles Turner (MIL)** on both 2026-10-21 and
  2026-10-23 — a rotation trait, not a one-night event.
- Repeat victim: **Cason Wallace (OKC)** — surged over by two different
  bench guards (Ajay Mitchell, Alex Caruso) in one game, 2026-10-22, after
  the opening-night game in which Jared McCain's bench usage coincided with
  Wallace scoring 4 first-quarter points and none after. (The opening-night
  surge *note* was lost in a mid-fix rebuild of the notes file; the final
  box score is preserved in the game file, event 401909090.)
- Two-victim game: **Darryn Peterson (UTAH)** lost usage to both Isaiah
  Collier and Ace Bailey in the same game (2026-10-21); he averages
  9.0 pts in 31 min/g — minutes without the ball.

## Finding 3 — 20+ unanswered runs are rare and segment-stamped

2 in 17 finals: **DET 23–0 from Q4** (2026-10-20 @ BOS) and **POR 21–0 from
Q1** (2026-10-21). Both are filed with their start period for the run-timing
research line; no predictive claim is made yet.

## Finding 4 — The steadiest scorers combine usage with foul discipline

Starters with 2+ starts, ranked by FGA/min with low PF/36: Tyler Herro 0.70
FGA/min (0.6 PF/36), Shai Gilgeous-Alexander 0.65 (1.0), Tyrese Maxey 0.51
(3.1). *Hypothesis:* will-score reliability is a two-factor read — attempt
rate × availability — not a scoring average.

## Retractions (read before citing the raw notes)

Events 401909840 (HOU @ DAL, 2026-10-21): the Naji Marshall and Zaccharie
Risacher "surges" over Daniel Gafford were **detector artifacts** — a
zero-attempt baseline starter and a 31-point blowout. The detector was
hardened the same night (see DETECTOR_SPEC.md changelog); Gafford's victim
count of 2 consists entirely of these artifacts and must be discounted.
Any consumer of `pattern_notes.jsonl` must apply the same discount until the
notes are regenerated under the hardened detector.
