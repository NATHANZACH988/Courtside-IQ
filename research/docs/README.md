# Research engine notes

Modules in `research/` implement transparent helpers for the NBA Intelligence Engine:

- `doctrine.py` — Play / Lean / Pass gates (5 banked games for Play unless owner override)
- `foul_trouble.py` — PF/36 and early-foul pressure → minute & opportunity penalties
- `streaks.py` — hot/cold z-score windows with modest self / teammate spillover priors
- `minutes.py` — combines foul + injury deltas into projected minutes
- `evidence.py` — source URL + observation timestamp records

These modules **do not** claim betting edges. Arena scoring does not consume streak
adjustments unless a separate, reviewed projection path freezes them into a baseline.
