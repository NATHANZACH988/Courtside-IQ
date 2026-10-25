# Courtside IQ — research-to-release operating system (v1)

**Status:** proposed process with machine-checkable structural gates, not an approved betting model or production release. The shared `docs/API_CONTRACT.md` is unchanged. This protocol complements `docs/AGENT_COLLABORATION.md`, `docs/FULL_ROSTER_PROP_SCREENING.md`, and the draft point-in-time evidence layer in PRs #8–9.

## 1. Mission and separation of concerns

Build an **information-first, multi-sport research system**, not a permanent NBA-only model. Sport-specific adapters gather facts; the common core records provenance, hypotheses, timeline, review status, and error corrections. Product/Prediction Arena code consumes only independently approved interfaces. Never let a market price silently change an independent on-court projection.

Maintain three separate outputs:

1. **Research evidence:** observations and hypotheses, including contradictions and retractions.
2. **Forecasting validation:** prospective predictions, grading against original frozen lines/baselines, calibration, and benchmark comparisons.
3. **Product scoring and releases:** a human-approved promotion. No research signal can self-promote into Play or production scoring.

The beta Prediction Arena remains a free, no-prize prediction competition. Historical betting research is not a claim of verified betting advantage or a license to redistribute sportsbook data.

## 2. Evidence lifecycle and authorization

| Stage | Minimum deliverable | Hard stop |
| --- | --- | --- |
| Discovery | Hypothesis, sport/market taxonomy, source discovery inventory, alternate explanations | Do not advertise a discovered pattern as predictive |
| Capture | Stable event/team/athlete IDs, raw snapshot digest, recorded UTC publication and capture times, source URL, rights status | Do not invent or backdate raw snapshots; source labels are assertions until audited |
| Prospective | Freeze hypothesis, coverage universe, exclusions/unresolved cases, model version, prediction timestamp before official event start | No post-tip edits to original forecasts; corrections are append-only |
| Evaluation | Full denominators (including failures, pushes/voids and pending), frozen protocol, matched settlement, walk-forward/out-of-sample metrics, negative controls | No historical selection of winners or last-known line substituted for offered line |
| Independent review | Reproduce data lineage/tests; leakage, calibration, identity, rights and security review | Unit tests alone are not predictive validation |
| Promotion | Owner approval + versioned contract change review if needed + monitored rollback | The gate module never authorizes production by itself |

All real-world research artifacts should record `observed_at`, `published_at`, `captured_at`, `effective_at`, `event_start`, `frozen_at`, and `graded_at` where applicable. Missing provenance is an explicit status, **not** inferred from a date-only file name.

The `research.quality.gates` manifest checker validates only *declared structural facts*. A SHA-256 string is a reference for future reproduction, not proof that an artifact exists or was collected when claimed. Source rights remain subject to independent examination even when marked `licensed`.

## 3. Daily research loop (applies by sport)

**Pregame:** inventory the **entire eligible universe** first, record all active/inactive/questionable/unknown statuses, independently project player/team opportunities, capture injuries, lineups, rest, venue and sources, then capture sportsbook lines as a separate channel. Freeze all candidate and rejected rows with timestamps. A legitimate slate may yield zero selections.

**Live:** watcher appends observations, lineup/game-flow changes, and source revisions. Never overwrites pre-tip predictions or retrospectively labels live discoveries as pregame edges. Escalate new contradictions and material injury/minute changes, not every routine game-flow event.

**Postgame:** capture independently verified finals and settlement rules, grade against original posted lines, preserve losers and voids, assign reasons to ungraded outcomes, publish corrections/retractions, then run drift and calibration reports.

**Weekly:** prospective-only comparison versus market implied expectations and simple baselines, broken out by sport, market, role, season and data source. Retire unsupported angles; collect failures as first-class evidence. No threshold tweaking on the same holdout results.

## 4. Sport adapters and point-in-time safety

- Common envelope: `sport`, provider-qualified `event_id`, team/athlete IDs, source URL, snapshots and timing, rule version, event status, rights and raw-payload digest.
- Sport adapters: vocabulary, eligible roster definition, opportunity metrics, substitutions, sport-specific settlement, season-boundary rules and data-source permissions.
- NBA: retain **five current-season banked games per team** before Play, absent explicit owner override; screen full game-day roster. The 2026-10-24 53 prediction entries are research hypotheses, not validated prop picks.
- NFL: starters and reserve snap/route usage, game states, targets, injuries and weather; do not reuse NBA minute assumptions.
- MLB: pitcher/batter lineups, projected starts, pitching changes, park/weather, plate appearances, opponent hand and official game status.
- NHL: goalie confirmation, projected lines, ice time, power-play role and scratches.
- Soccer: confirmed lineups, starting status, minutes risk, competition-specific stat definitions, substitutions, cards and match status.

Attribution to ESPN or any other provider must distinguish an accessible endpoint from **contractual permission for commercial use**. Keep network/provider adapters isolated from downstream scoring and enforce HTTPS/credential hygiene and rate/cost limits.

## 5. Historical odds and tickets: source-complete before claims

Persist both winning and losing settled outcomes, full pregame market availability where available, sportsbook, market period, side, exact line, American/decimal odds, settlement/void rules, timestamps and raw source pointer. Winning slips alone suffer publication-selection bias. Never treat a quote lacking side, period or rule as a settled wager (see PR #9). A market observation captured after event start cannot be replayed as pregame.

Required research comparisons: no-vig baseline where possible, price/line sensitivity, opening-vs-available-vs-closing snapshots, walk-forward holdout windows, vig-adjusted return, calibration, sample uncertainty and selection bias. Separate **observed outcomes**, **model forecasts**, and **chosen bets**.

## 6. Code and bot collaboration

1. Create one issue/PR for one independently useful lane; identify parent branch and dependent PRs. Avoid long stacks where possible.
2. **Pax:** prospective game-flow / source observation and hypothesis collection. **Other engineering bots:** Arena/application implementation or sport adapters on separate branches. **Independent reviewer:** chronology, security, data rights, API compatibility, identity, tests, scoring integrity.
3. PR template: exact touched surfaces, commands and logs, provenance and rights, real-vs-fixture data distinction, API contract impact, security impact, migration/rollback, baseline/holdout evidence, unresolved decisions.
4. Draft until independently reviewed. Changes to `docs/API_CONTRACT.md` require both responsible agent reviews and explicit owner authorization; no self-merge.
5. Retest merge-base compatibility after each parent merge. A passing CI check on a stacked branch is **not** proof that all siblings can safely merge.
6. Before public deployment: enforce authentication, tenant isolation, privileged cron mutation, secrets handling, append-only forecasts, trusted event locks, normalized settlements, health monitoring and rollback; do not use demo login in production.

## 7. Test pyramid and reporting

- **Unit:** deterministic boundary tests for parsing, identity, duplicate/retracted records, late timestamps and market settlement.
- **Contract/integration:** source schema drift, provider outages, idempotent ingestion, API response compatibility, event-lock concurrency, permissions.
- **Fixture regression:** known false positives and contradictory NBA prediction artifacts; be explicit that synthetic fixtures are not independent backtests.
- **Prospective evaluation:** newly frozen predictions only, full denominator, untouched holdout, market baselines, calibration and model drift.
- **Security/release:** authZ, no mutable GET endpoints, secret leaks, supply-chain versions, mobile and accessibility tests and rollback.

Report each PR as **implemented / tested / independently verified / awaiting owner decision**. Quote exact run IDs and test counts only after inspecting CI evidence. Never claim a passed test proves commercial data rights, forecasting accuracy, or a profitable model.

## 8. Automation and how to use the structural auditor

Run the checker against a JSON manifest with a source, prospective, or evaluation threshold:

```bash
python -m research.quality.gates path/to/manifest.json source
python -m research.quality.gates path/to/manifest.json prospective
python -m research.quality.gates path/to/manifest.json evaluation
PYTHONPATH=. python -m unittest discover -s research/tests -p 'test_*.py' -v
```

Schema v1 fields:

- `schema_version=1`, `study_id` (provider-qualified), `sport`, `hypothesis`.
- `sources[]`: unique `source_id`, HTTPS `url`, `published_at_utc`, `captured_at_utc`, `raw_sha256`, `rights_status`.
- `freeze`: sport-qualified `event_id`, `as_of_utc`, `event_start_utc`, `artifact_sha256`.
- `coverage`: nonnegative `eligible`, `screened`, `excluded`, `unresolved` summing to eligible; `rejection_reasons_recorded=true`.
- `evaluation`: `frozen_predictions`, `graded`, `voided`, `pending` with a complete denominator; `holdout_events`, `report_sha256`, `protocol_sha256`, `protocol_frozen_at_utc`, `report_generated_at_utc`.

The evaluator reports granular reason codes and always sets `production_authorized=false`. A structurally complete manifest **does not imply** the evidence is authentic, correctly licensed, representative, predictive, statistically significant, or suitable for deployment.

## 9. Priority order / owner decisions

**P0:** independently review/sequence existing PR #1–#9; resolve demo-auth and privileged cron blockers; make research tests non-skippable once committed; require event/athlete identity and point-in-time provenance.

**P1:** choose licensed capture providers and store reproducible raw receipts; integrate NBA + NFL sport adapters to the shared evidence envelope; grade prospective forecasts across frozen denominators; fix Pax's name-based player joins and same-day post-tip freezes.

**P2:** historical market line + side/period/settlement schema proposal (not the shared API contract), odds backtesting with losers, contradiction and hypothesis-retirement registry, independent multi-sport dashboard.

Decisions reserved for owner: provider rights/budget, contract promotion, production Play eligibility overrides, deployment, and merges. Everything else should advance on isolated, reviewable branches.
