# Prospective mechanism-log chronology audit (research-only)

The prospective prediction builder on Pax PR #6 checks the calendar date, but a same-day build can still be created after a particular game's tipoff. It also reads a generated full-roster board without independently proving that all input finals preceded the target tip. Do **not** interpret a self-declared `frozen: true` flag as independently verified pregame evidence.

This add-only validator works on the original `predictions-YYYY-MM-DD.json` format without changing Pax's code or the shared API contract:

```bash
python research/provenance/pregame_prediction_audit.py path/to/predictions-2026-10-24.json
python -m unittest discover -s research/tests -p 'test_pregame_prediction_audit.py' -v
```

It rejects malformed or ambiguous JSON, nonfinite bank statistics, duplicate player/mechanism/event entries, conflicting event metadata, post-tip build/log timestamps, invalid direction/mechanism pairs, and postgame grades inside a frozen pregame file. Each predicted tip must also fall on the declared NBA slate date in `America/New_York` (including evening games whose UTC tip is on the following day). This is a self-declared consistency check, not an official schedule lookup; special international-date exceptions require explicit review. It also rejects empty prediction cohorts, missing or invalid calendar dates, invalid declared scheduled-game counts, and cases where distinct prediction events exceed the declared game count.

**Limitations:** timestamps are self-reported; they can be forged. The validator cannot independently attest when a file was created, authenticate the ESPN game bank, prove source licensing, or show that the full-roster board excluded games completed after the forecast cutoff. It intentionally returns `independent_timestamp_verified: false`, `pregame_bank_cutoff_verified: false`, and `cohort_coverage_verified: false` even when all declared chronology checks pass. True pretip audit requires an independently timestamped archive plus a per-source, per-game input manifest with captured/finalized timestamps and hashes.

The test fixtures are synthetic; they do not establish prediction accuracy or backtest performance. Existing historical scores are not revised. Do not promote any mechanism to a Play based on this validator.
