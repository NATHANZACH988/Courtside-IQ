# Paired prospective evaluation — multi-sport research-only

The standalone `research.quality.paired_evaluation` module compares **the
same frozen player-event forecasts** against their contemporaneously frozen
independent baseline after outcomes are recorded. It is additive to the
research-to-release process in draft PR #10, not a change to the shared API
contract or NBA/Prediction Arena scoring.

## Why this exists

Pax's October 25 agency report (PR #11) reports that, for its first graded
mechanism hypotheses, simpler naive projections outperformed shrunk and
mechanism-adjusted NBA forecasts. The reported 53 forecast outcomes were
6 HIT, 45 MISS and 2 NO_DECISION. These are **author-reported** findings:
the raw agency snapshots, baseline freezes, full game-day roster and grading
reproduction artifacts are not committed with that documentation. We cannot
treat this as verified prospective accuracy until the original evidence can
be reproduced. A separate first-pass research pipeline must not silently
replace the reported 2026-10-24 grading rules.

This checker is deliberately **not an odds or winning-ticket engine**. It
measures paired absolute forecast error for numeric sport-specific markets,
not whether an over/under beat an actual offered sportsbook line. A
`no_decision` or `void` is retained in the full denominator but is not
included in the paired mean absolute error. Incomplete/pending cohorts are
clearly marked.

## Input requirements (JSON schema version 1, code-enforced)

A JSON batch contains:

- `batch_id`, `sport`, `market`, `model_version`,
  `baseline_version`; stable provider-qualified identifiers
- `frozen_manifest_sha256`, `baseline_artifact_sha256`,
  `evaluation_protocol_sha256`: declared raw artifact digests, *not*
  independently verified receipts
- `evaluation_protocol_frozen_at_utc`,
  `frozen_manifest_at_utc`, `evaluated_as_of_utc`: timezone-aware UTC
  timestamps in nondecreasing order
- `expected_forecast_ids`: the *original* complete frozen forecast IDs;
  missing, duplicated, or added IDs invalidate the batch
- `forecasts[]`: unique `forecast_id`, sport-scoped `event_id`,
  provider-qualified `athlete_id` and `team_id`, matching `market`,
  `scheduled_start_utc`, `frozen_at_utc`,
  `training_data_as_of_utc`, `baseline_frozen_at_utc`,
  `baseline_data_as_of_utc`, `predicted_value`,
  `baseline_value`
- `settlements[]`: one per forecast ID, identical
  event/athlete/team/market identity, and one of
  `final` / `void` / `pending` / `no_decision`.
  **Final** requires a finite `actual_value` plus HTTPS `source_url`,
  `published_at_utc`, `captured_at_utc`, and `raw_sha256`.
  Voids/no-decisions require a source receipt but no numeric actual.
  Pending requires `actual_value: null` and no settled-source receipt.

The checker also rejects:
- Predictions or baselines frozen after the allowed pregame cutoff; any
  source/training data that is declared to exist after its freeze;
- Duplicate player-event-market entries or the same player simultaneously
  associated with competing teams in one event;
- Missing/nonfinite values and enormous numeric values that are not plausible
  sport stats;
- Settled results captured in the future relative to the evaluation run,
  or finals supposedly captured before the event began;
- Invalid, duplicate, missing or unmatched settlement identities.

## Interpretation of results

The module returns `model_mae`, `baseline_mae`, and
`paired_mae_improvement = baseline_mae - model_mae` **only over the same
nonvoid graded forecasts**, with winning/tied comparisons and full counts.
A positive value means the model had lower absolute error *on that cohort*;
it is not evidence of a betting edge or statistical significance.

Outputs **always** include `production_eligible=false` and
`scoring_eligible=false`, even when structurally valid and evaluation is
complete. This module has no access to external licenses, authentic
historical archives, independent holdout selection, candidate-universe
coverage, or model calibration. Those require the separate process and
human gates. A descriptive `evaluation_complete=true` does not establish
sample sufficiency or prospective predictive skill.

A numeric player-stat forecast must not be labeled a Play by this module.
NBA retains the owner-set five-current-season-banked-games-per-team gate,
full-roster screening, line sourcing and point-in-time injury verification.
Other sports need their own sport-specific research/eligibility rules.

## Run

```bash
PYTHONPATH=. python -m unittest discover -s research/tests -p 'test_*.py' -v
python -m research.quality.paired_evaluation research/examples/paired_batch_synthetic.json
```

The sample JSON is **invented** to test the wire format and expected error
calculations, not real athlete outcomes or sports data.

## Recommended next integration (not implemented in this PR)

1. Export Pax's **original** 53 frozen predictions and pregame baseline
   snapshots without modifying the historical file, including stable IDs and
   source receipts. Preserve all misses and no-decisions.
2. Independently verify original timestamps and attach reproducible raw
   game bank and event-scoped official roster evidence.
3. Adapt an NFL numeric-market research cohort through this same envelope;
   define its season and eligible-roster gates independently.
4. Run holdout comparisons by sport/market and event-level blocks to avoid
   treating correlated same-game player outcomes as independent observations.
   Add calibrated uncertainty and baseline/market benchmarks before proposing
   a model promotion.
5. Route any scoring proposal through shared-contract cross-agent review and
   owner authorization; do not automatically merge research branches.

### Source and safety

No external calls, credential handling, scraping, money movement, or
production scoring. Only the optional CLI reads a user-selected JSON file.
Captures and digest labels are declared evidence, not verified authenticity
or commercial-use permission. Result receipts are not real sportsbook quotes.
