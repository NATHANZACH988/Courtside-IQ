# Cross-report claim audit (research-only)

Pax's October 25 lab findings in PR #11 introduce useful **negative results**:
the 53 frozen mechanism hypotheses reportedly graded 6 HIT, 45 MISS, 2 NO_DECISION,
and the naive projection reportedly beat the shrunk and mechanism-adjusted
projections. These are **author-reported** until the agency code, raw bank,
original freeze, grading rules and complete denominators can be independently
reproduced. PR #11 contains documentation only; its green CI run skipped
both test directories.

The ticket archaeology work is a **synthetic construction study**:
one-prior-game averages were used as proxy lines. No historical sportsbook
prices, true market availability, settlement rules or vig are demonstrated.
Do not label proxy wins as winning real tickets or use the rates to claim
positive expected value.

## What this module does

`research.quality.claim_audit.audit_claims` and the command-line checker
validate a versioned claim manifest. It enforces:

- Stable claim/dataset/cohort/method identities and raw/method SHA-256 **claims**.
- Code revision, reproduction command, source URL and declared rights status.
- Explicit numerator and denominator, sample frame, and no winner-only
  population extrapolation.
- Separate kinds: observational, proxy_ticket, actual_ticket, prospective_forecast.
- Real-ticket claims require actual posted line, sportsbook, side, period,
  odds, settlement version and a captured quote before the event.
- Predictive claims require frozen artifact, protocol frozen no later than
  the forecast, pre-event freeze and nonzero holdout events.
- Corrections to the **same dataset/cohort** require an explicit
  `supersedes` link, with the old claim marked superseded. Different cohorts
  may legitimately yield 2/2 and 2/8; each must have a distinct cohort ID,
  eligibility filters and documented scope.

It returns `structural_ready`, `independently_verified`, and
`scoring_eligible`. The latter two are **always false**, even if the
structure passes. A hash string or a rights label does not prove the underlying
artifact was captured when claimed, nor does it authorize commercial use.

## Example workflow

1. Record each research claim as a JSON object in `claims[]` with
   `schema_version: 1`. Store the source and method artifacts independently.
2. Run `python -m research.quality.claim_audit path/to/claims.json`.
   Exit 0 means structurally complete; exit 1 lists reason-coded blockers.
3. A reviewer verifies the referenced files, digests, timestamps, licenses,
   participant/roster identities, denominator and method by independent replay.
4. Retain old claims, link corrections using `supersedes`, and publish both
   original and revised grading. **Never rewrite the original prospective score.**
5. Promotion into scoring remains owner-controlled, subject to the five
   current-season banked NBA games per team and the full-roster screen.

### Required manifest fields

For each claim: `claim_id`, `claim_key`, `dataset_id`, `cohort_id`,
`method_id`, `dataset_sha256`, `method_sha256`, `code_revision`,
`reproduce_command`, `source_url`, `rights_status`,
`kind`, `scope`, `status`, `numerator`, `denominator`,
`sample_frame`, and optionally `supersedes`. Proxy-ticket claims
require `line_kind: proxy`. Actual-ticket and prospective-forecast claims
require the additional fields described above.

## PR #11 independent review items

- **Reported 53:** reproduce the frozen artifact, grader, per-entry verdicts,
  6/45/2 denominator, conflicting directional signals, and original timestamps.
- **Reported MAE:** reproduce all 141 eligible rows, 127 graded rows, DNP
  exclusions, player/event joins and naive/adjusted error calculations.
- **2/2 vs 2/8 victim persistence:** record distinct cohorts, eligible
  follow-up games and chronology; supersede misleading generalizations.
- **Ticket shapes:** reproduce all 42 constructed tickets, 254 legs and
  overlapping event exposures; use original odds/lines only when available.
- **Sources:** source-specific terms, observed/captured timestamps and
  independently verified licensing are still required before automated
  collection from betting/social platforms.
- **Rule changes:** pair-based CANNIBAL grading is a new version for future
  freezes. Any retrospective regrade must be explicitly labeled sensitivity
  analysis, not silently substituted for the 6/45/2 baseline.

This module performs no network I/O, stores no credentials, does not alter the
shared API contract, and does not interact with Arena or production scoring.
