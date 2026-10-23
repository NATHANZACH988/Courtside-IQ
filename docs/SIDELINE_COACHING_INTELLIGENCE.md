# Courtside IQ — Sideline Coaching Intelligence

**Status:** Development specification, not an implemented or validated model.

## Objective
Analyze basketball like a sideline analyst and coaching staff: assess each player's execution in context, anticipate the actual coach's substitutions and adjustments, and estimate the resulting effects on every player's minutes and statistical opportunities. Keep **predicted coach behavior** separate from **model-recommended optimal decisions**.

## 1. Player performance evaluation
Evaluate by role, matchup, lineup and game phase:
- Offensive: usage, possessions, touches, shot selection and quality, efficiency, rim pressure, playmaking, turnovers, screens and off-ball movement (only where licensed data permits).
- Defensive: assignments, foul discipline, contests, rebounding position, rim protection, matchup performance and team defensive context.
- Availability and workload: foul count and foul-out risk, rest, minutes, rotation stint length, fatigue proxies and reported injury restrictions.
- Hot/cold performance: separate shot-making variance from changing shot quality, volume, coaching trust or opponent defensive attention.
- Grade **decisions and role execution** separately from raw box-score outcomes; use an evidence/coverage flag for unavailable tracking metrics.

## 2. Coach and rotation forecasting
- Build coach-specific historical substitution tendencies, normal rotation trees, closing lineups and matchup substitutions using point-in-time data.
- Forecast who enters when a starter sits for fouls, fatigue, injury or poor performance.
- Estimate minute reallocations and lineup-specific usage/shot/assist/rebound shifts; reconcile team minutes and opportunities.
- Account for score margin, pace, quarter, time remaining, timeout patterns, back-to-backs and opponent adjustments.
- Distinguish what a coach **is likely to do** from what an optimization model **would recommend**; do not present either as certain.

## 3. On-court ripple effects
Represent dependencies across the five players on each team and opponents:
- Foul trouble → replacement lineup → rim defense/rebounding changes → opponent shot mix and teammate opportunity shifts.
- Hot scorer → defensive attention or doubles → changed assists, shot distribution and open looks.
- Cold shooting or poor decision-making → possible substitution or altered role, only when supported by coach behavior evidence.
- Lineup and pace shifts → correlated statistical distributions rather than independent player forecasts.

## 4. Analysis products
- Pregame: expected rotation map, role grades, matchup pressure points and scenario-weighted minute/stat distributions.
- In-game research: observed events, likely next substitution/adjustment and evidence-based forecast deltas.
- Postgame: coaching-style film-room report, player role grades, what actually changed, forecast error attribution and lessons for next game.
- Show uncertainty, data source URLs, timestamps, coverage, and model version. Do not claim to have watched film or tracked off-ball actions unless those inputs actually exist.

## 5. Validation and guardrails
- First establish the core slate → lock → official result → grade workflow.
- Develop the coaching model incrementally: rotation baseline, foul scenarios, lineup dependencies, then evidence-tested hot/cold and adjustment effects.
- Backtest out of sample by coach/team, compare against simple minute/usage baselines, test calibration and feature ablations; reject signals that fail.
- Avoid hindsight leakage: frozen pregame projections and Arena submissions never change after lock. In-game analysis is separately timestamped.
- Keep the Arena's accuracy scoring independent from subjective coaching grades.

## Suggested initial engineering tasks
1. Define source-attributed possession/game-state and substitution event schemas.
2. Implement rotation-stint and foul-state features from permitted play-by-play data.
3. Build coach-specific next-substitution and remaining-minutes baselines.
4. Add scenario-based teammate/opponent opportunity redistribution with conservation checks.
5. Create postgame coach-style report with evidence-backed grades and error breakdown.
6. Add unit tests for substitution changes, foul-out constraints, lineup minutes, and no look-ahead leakage.
