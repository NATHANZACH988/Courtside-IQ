# Independent NBA grading-source integrity review (2026-10-25)

**Target:** Pax's full-roster prediction engine, PR #6, and its gameflow
watcher parent PR #4. This branch is an **additive, read-only audit**.
It does not change the frozen 53, any HIT/MISS rule, API contracts, or
production scoring. It is a sibling to PR #7 and PR #16, not a replacement.

## Reproduced correctness risks in the other bot's code

1. **Wrong-team player joins can flip a grade.** In
   `research/gameflow/prediction_log.py`, `grade_entry` uses
   `next(p for p in players if p["name"] == e["player"])` without
   checking `e["team"]`. A synthetic final with two same-named athletes
   (opposing teams) grades the wrong athlete as HIT even though the
   predicted athlete's own performance is a MISS. The full-roster
   aggregator also groups by display name alone. Real stable athlete
   IDs and verified game-day team assignments are not yet present.

2. **CANNIBAL blowout exclusions are silently skipped.** The watcher
   (`research/gameflow/gameflow_watch.py`) produces `teams` and
   `segment_scores`. The grader checks `final.get("segments", [])`,
   which the watcher does not emit. Consequently the intended
   20-point margin exclusion is never evaluated on that watcher schema.
   A synthetic 125–95 final containing a valid bench surge grades HIT,
   although the rule says a 30-point blowout should be NO_DECISION.
   This is a demonstrated contract mismatch **inside the research
   pipeline**, not a change to the shared HTTP API contract.

3. **Withdrawn/wrong-team foul notes can become false hits.**
   FOUL_CAP grading checks a player's name and the substring `foul`
   in the note type, without checking note team or retraction state.
   A synthetic final with 1 personal foul and a withdrawn
   `foul_trouble_cap` note grades HIT. This undermines the earlier
   retracted-detector evidence precautions in PR #5.

These are **synthetic, source-code reproducible** defects. They do not
prove that any particular historical prediction was misgraded: the
underlying agency gameflow finals and source receipts were not
included in PR #6.

## New read-only module

`research.integrity.grade_source_audit` accepts a frozen prediction
and a watcher final, or a frozen batch and a map of event IDs to
finals. It reports:

- exact ESPN event ID, NBA league, final status and team-score validation;
- predicted matchup and athlete-team membership;
- name-only player collisions, duplicate rows and wrong-team joins;
- watcher/grader CANNIBAL margin field mismatch and actual >=20 margin;
- wrong-team or withdrawn FOUL_CAP notes;
- absent player records as NO_DECISION-expected rather than fake misses;
- declared source-receipt gaps and missing stable athlete IDs;
- total/pending/unsafe denominator counts without dropping bad rows.

`safe_for_legacy_grader` means **only** that this narrow structural
check found no known blocker. Every result sets
`source_independently_verified=False` and
`production_scoring_authorized=False`.

### Running on local copies (no network or mutation)

Create a JSON object `FINALS_BY_EVENT.json` mapping ESPN event ID
strings to the watcher final objects. The frozen batch is the exact
original `predictions-DATE.json`, never a graded or revised file.

```bash
PYTHONPATH=. python -m research.integrity.grade_source_audit \
  /path/to/predictions-DATE.json /path/to/FINALS_BY_EVENT.json
PYTHONPATH=. python -m unittest discover -s research/tests -p 'test_*.py' -v
```

The CLI exits nonzero on any unsafe source or pending event. It prints
a detailed JSON report and **never** writes grades or accesses the network.

## Blockers / merge sequence

- Require stable athlete IDs in the watcher and board, plus immutable
  event/team identity crosswalks; reject name-only joins before scoring.
- Reconcile `segment_scores` and the grader's `segments` expectation
  in a separately reviewed grading-rule change, including exact
  20-point boundary tests and historic grade revision lineage.
- Enforce note retraction, event/team scope and evidence revision IDs.
- Obtain immutable ESPN source payloads, observed/captured timestamps,
  provider-rights review and complete historical final datasets.
- Run prospective baseline comparisons on the **entire** frozen cohort;
  no proxy-line ticket profitability claims and no NBA Play promotion
  before the five-banked-games-per-team and owner gates.

This audit should be reviewed before promotion of Pax's graded hit
rates. **Do not automatically rewrite the original October 24 grades.**
Any corrected grades must preserve originals and explicitly link
revisions, as proposed in draft PR #16.

## Test scope

Synthetic unit tests intentionally reproduce the legacy grader's
incorrect HIT outcomes, then assert that the new audit flags those
inputs. Tests also cover malformed finals, mismatched events/teams,
untrusted source receipt claims, and pending denominator preservation.
They do not backtest actual sportsbook lines, real ticket outcomes,
or predictive edge.
