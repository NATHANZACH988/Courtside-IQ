# Game-flow detector specification

Implementation: `research/gameflow/gameflow_watch.py` (observation) and
`research/gameflow/scoring_profiles.py` (aggregation). Data source: ESPN
summary JSON per game (unofficial feed; no SLA; scores/box scores/plays).

## Detectors (post-hardening, 2026-10-21)

**Foul-trouble cap.** A player with ≥4 personal fouls in ≤20 minutes played.
Rationale: the 4th foul is the substitution trigger; the cap shows in the
scoring line the same night.

**Bench usage surge.** A non-starter with ≥8 minutes, ≥6 points, and
FGA/min ≥ 0.45, whose FGA/min is ≥1.5× the lowest-rate same-position
starter (the "slot starter", who must have ≥8 minutes and ≥2 FGA), with
the bench player's points ≥ the slot starter's, **and** game margin < 20
(garbage-time rotation is not usage theft).

**Unanswered run.** Consecutive scoring plays by one team totaling ≥10
points with no intervening opponent score; start period recorded. Runs
≥20 are flagged `remarkable`.

## Reporting rule (chat surface)

Silent by default. Surface only (a) a new 20+ unanswered run, or (b) a
bench surge that **persists into the second half** (flagged in an earlier
run of the same game and again while the game is in period ≥3). First-half
surges are logged, never surfaced — small-minute rates are noise.

## Aggregation

`scoring_profiles.py` reads Final game files only, plus the notes file
deduped by (event, type, player). Rates: FGA/min, PF/36, pts/g, min/g.
Flags: `foul_risk` at PF/36 ≥ 4.8; event counts for capped / cannibal /
victim.

## Known limits

- Positions are ESPN's coarse G/F/C — "slot" is approximate within a
  position group, not a true substitution pairing.
- Minutes are whole-minute resolution from the feed.
- The notes file appends per run; consumers must dedupe as above.
- No tracking data (no shot quality, no defensive assignment ground truth);
  the "eraser" effect (e.g., a rim protector deleting a shot profile) is
  currently analyst-observed, not detector-measured.

## Changelog

- 2026-10-20 v1: caps, surges (raw rate test), runs.
- 2026-10-21 hardening: surge requires ≥6 bench points, slot starter ≥2
  FGA (kills zero-rate baselines), margin <20 (kills blowout artifacts);
  reporting bar raised to second-half persistence after first-half flags
  proved noisy. Two false positives from v1 are named in the findings doc.
