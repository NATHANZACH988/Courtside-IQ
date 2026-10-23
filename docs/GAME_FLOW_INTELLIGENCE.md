# Game Flow Intelligence — research and beta roadmap

Status: research specification; not a claim that these models are implemented or validated.

## Foul trouble and rotations
- Track player foul count, game period, minutes played, expected minutes remaining, and team foul situation when available.
- Model substitution likelihood and foul-out risk conditioned on player role, coach rotation behavior, score, and time remaining.
- Reallocate projected minutes and opportunities to actual replacement candidates; avoid assuming every replacement receives the same usage.
- Model effects on teammates and opponents (rim protection, matchup switches, defensive pressure, pace and shot mix).
- Distinguish pregame foul-risk distributions from in-game observed foul events. No retroactive changes to frozen predictions.

## Hot/cold shooting and game flow
- Track observed shot attempts, shot quality where licensed, make/miss sequences, shot selection, playing time, usage, and defensive matchups.
- Evaluate whether hot/cold streaks add predictive information beyond baseline efficiency; do not assume shooting streaks imply persistent hot hands.
- Model coaching and opponent responses: defensive attention, double teams, substitutions, play calls, and redistributed assists/rebounds/attempts.
- Represent uncertainty and distinguish causal mechanisms from noisy short samples.
- Evaluate with out-of-sample tests, calibration, ablations, and timestamped features to prevent outcome leakage.

## Multi-player dependency model
- Minutes on court and team opportunities must reconcile to realistic totals.
- Simulate scenarios for foul trouble, rotation changes, blowouts, pace, hot/cold shooting, and defensive adjustments.
- Preserve correlation between player outcomes and ensure scenario probabilities sum to 1.
- Report forecast deltas with explanations and evidence quality, not fabricated precision.

## Integration
- Research engine owns these models; Arena scoring and game locks remain unchanged.
- Live scenario updates may inform a separate in-game research view but cannot alter locked contest forecasts or baselines.
- Add data provenance, source timestamps, model version, and backtest results to any published scenario.
- Build as phased, evidence-gated features after the core slate-to-grading vertical slice.
