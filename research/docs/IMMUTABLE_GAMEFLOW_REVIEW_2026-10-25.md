# Independent game-flow freeze and grading integrity review — 2026-10-25

**Review target:** Pax's `pax/full-roster-predictions` (PR #6).  
**Scope:** fail-closed persistence and chronology guards only. The original
FOUL_CAP, CANNIBAL, VICTIM and STEADY selection and grading rules remain
unchanged, as do the original 53 frozen 2026-10-24 predictions.

## Reproduced from source inspection

1. `cmd_build` originally rejected **past dates** but permitted a freeze on
   today's date *after tipoff*. A retrospective batch could therefore be
   labeled `frozen: true` even if games had started.
2. `cmd_build` checked `os.path.exists` then wrote with `open(..., "w")`.
   A concurrent run could overwrite a previously frozen manifest between
   the existence check and write.
3. `cmd_grade` always wrote the same `predictions-DATE-graded.json` using
   `open(..., "w")`. A second run after source corrections or grading
   changes silently destroyed the original graded result. This is a serious
   obstacle to honest forward-only evaluation.
4. `cmd_grade` did not validate the frozen flag, per-entry pretip timestamps,
   or whether an input prediction already carried a grade.

## Implemented

- Validate ISO calendar dates before they become file paths.
- Reject empty/malformed schedules and **any** event whose stated tip is at
  or before the actual build time; repeat the pretip check immediately before
  creating the manifest. No partial-game or after-tip cohort is emitted.
- Use exclusive-create mode (`open(..., "x")`) for the initial freeze and
  original grade. A race or repeat invocation fails rather than overwrites.
- Require a frozen input, nonempty predictions, valid timezone-aware build,
  log and tip timestamps, `logged <= built < tip`, and no embedded grade.
- Record the SHA-256 of the actual input full-roster board bytes, plus a
  SHA-256 of the **derived ESPN schedule projection**. These are useful
  change-detection checksums, **not independently trusted timestamp receipts
  or raw ESPN response evidence**.
- Allow a later grade only with explicit
  `grade --date YYYY-MM-DD --revision SAFE_ID --reason "why"`. Its output is
  a **new** `predictions-DATE-graded-SAFE_ID.json` and includes the original
  grade file's SHA-256, revision ID and reason. Existing graded files remain
  unchanged. Invalid revision names, missing reasons and missing original
  grades fail closed.
- Synthetic regression tests exercise pretip boundaries, malformed clocks,
  date traversal, same-day post-tip attempts, duplicate writes, late frozen
  inputs, original grade preservation and explicit revision lineage.

## Commands

```bash
PYTHONPATH=. python -m unittest discover -s research/tests -p 'test_*.py' -v
python research/gameflow/prediction_log.py build --date YYYY-MM-DD
python research/gameflow/prediction_log.py grade --date YYYY-MM-DD
python research/gameflow/prediction_log.py grade --date YYYY-MM-DD \
  --revision corrected-finals --reason "settlement source corrected"
```

## Limits and remaining blockers

- **No evidence authenticity attestation.** Files and clock readings are local
  and can be manipulated by someone with write access. A SHA-256 alone does
  not prove a pregame capture; use externally anchored, immutable raw receipts
  and audit logs before claiming independently verified prospective accuracy.
- **No complete game-day roster or stable athlete crosswalk.** Pax's board
  still aggregates by display name; injury, lineup and eligible-player
  universes are not independently verified. See the sibling PR #7 audit.
- **No historical offered lines or prices.** These are mechanism predictions,
  not verified sportsbook picks, and no actual bets are settled here.
- **Grading rule flaw remains frozen.** The CANNIBAL rule reported by Pax on
  Oct 25 can misclassify successful pair outcomes. Do not change the original
  rule or retroactively reclassify the 53; version a new pair metric
  prospectively in another PR.
- **No full source security review.** ESPN's public feed is used in Pax's
  source, but its reuse/commercial rights and response integrity have not
  been verified here. These guards do not add any new network access.
- **No change to `docs/API_CONTRACT.md` or Arena scoring.** This is research
  CLI-only behavior. Later grading revisions require an explicit new filename,
  so any downstream consumer expecting to reread a mutable `-graded.json`
  must be updated to ingest revision lineage explicitly.
- **Atomicity limit:** exclusive-create protects against replacement, but an
  interrupted JSON write can leave a partial new file. Future durable storage
  should use fsync + temporary files + atomic no-clobber publication.

The existing PR #6 should not be merged as production research infrastructure
until pregame provenance, independent source receipts, full-roster identity,
grading protocol versioning, and reviewer sign-off are resolved.
