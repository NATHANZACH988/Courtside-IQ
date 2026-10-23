# Closeness scoring — version `closeness-v1`

**Status:** Implemented for beta. Changes to philosophy require owner approval.

## Goal

Map absolute prediction error to a score in **[0, 100]** where 100 is exact.
Statistical categories use different error scales so that being off by 3 rebounds
is not treated identically to being off by 3 points.

## Formula

```
error = abs(predicted_value - actual_value)
score = max(0, 100 * (1 - error / scale[stat]))
```

Scores are rounded to 2 decimal places with banker's rounding (`round(x, 2)`).

## Category scales (`closeness-v1`)

| Stat | Scale | Rationale (beta) |
|------|------:|------------------|
| PTS  | 12.0  | Points vary more night-to-night |
| REB  | 6.0   | Tighter typical absolute error |
| AST  | 5.0   | Assist counts are lower-variance |
| FG3M | 3.0   | Made threes are sparse |
| STL  | 2.5   | Low-count defensive stats |
| BLK  | 2.5   | Low-count defensive stats |
| TOV  | 3.0   | Turnovers |

Unsupported stats raise `UnsupportedStatError` rather than silently defaulting.

## Experimental skill score (not for beta rankings)

When a question freezes a baseline `B` at slate creation:

```
user_score   = closeness(predicted, actual)
baseline_score = closeness(B, actual)
skill_delta    = user_score - baseline_score
```

Beta leaderboards rank by **mean accuracy** (`user_score` average) with sample-size
provisional marking. Skill deltas are displayed separately and never determine rank.

## Sample-size adjustment (beta rankings)

- `n` = completed graded predictions for the ranking window
- Provisional when `n < 5`
- Displayed mean is the raw mean; UI marks `provisional: true`
- Future shrinkage (e.g. Bayesian toward league mean) is deferred; do not invent it silently

## Versioning

`scoring_version` is stored on every slate and every grade row. Regrading uses the
slate's frozen version unless a commissioner explicitly requests a version bump
(audit event required).
