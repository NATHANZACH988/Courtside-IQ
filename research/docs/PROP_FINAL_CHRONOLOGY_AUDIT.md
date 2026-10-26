# Player-prop final-state chronology: independent review of PR #18

## Reproduced integrity gap

The original `compare_observed_stat` in draft PR #18 can label a
player-prop as `selected_over` or `selected_under` using a stat
published **during the game** if the caller sets `game_final=True`.
It requires only a source capture after the scheduled start, not after
the actual final whistle. A fabricated fixture with scheduled tipoff
20:00, an in-game stat published 20:05, and `game_final=True`
would be accepted as a mathematical win. This is a code-level
chronology issue, **not evidence that any real NBA prop was misgraded**.

## Additive audit, no changes to original grader

`research.props.final_chronology_audit` provides:

- `EventFinalReceipt`: event and both team IDs, a declared final
  timestamp, a source receipt, and explicit `final` status.
- `audit_prop_outcome_final`: wraps PR #18's research-only
  comparison but refuses to expose a mathematical win/loss/push
  unless the separately sourced final event time is later than
  scheduled start and no later than review cutoff, the final-event
  source was published and captured at/after that final time,
  and any player-stat source was also published and captured
  at/after the final time.
- Cross-checks event/home/away identity, inherited player/team,
  market/period and original pretip quote identity. Invalid
  records carry explicit reasons and **no numeric actual stat**.
- Unknown outcomes stay unresolved; DNP still needs a bookmaker's
  explicit settlement rules.

This deliberately **does not** change `compare_observed_stat` or
any historical grade; consumers must explicitly opt in to the
additional read-only audit. It is intended as a reviewable gate for
future integration, not a substitute for the original prediction
ledger or bookmaker settlement.

## Test command

```bash
PYTHONPATH=. python -m unittest discover -s research/tests -p 'test_*.py' -v
```

All fixtures are synthetic, including an in-game false-final
reproduction and legitimate post-final controls. There is no
sportsbook access, real historical NBA backtest, proof of data
licensing, official game-final authentication, or source checksum
verification.

## Remaining blockers and decisions

1. **Trusted final receipt**: authoritative, licensed event
   feed with stable event/team IDs and independently captured
   source timestamps; a caller-supplied `final_at` is only a claim.
2. **Corrections**: versioned post-final stat corrections and
   supersession history must be handled before any performance
   denominator is published. Do not silently overwrite a prior
   grade or drop DNP/unresolved outcomes.
3. **Settlement rules**: original bookmaker market and period,
   void/cancellation/overtime/DNP conditions and official
   settlement remain outside this module.
4. **Integration**: independent review of PR #18 and its
   PR #10 process-gate base. This PR is stacked on #18 only
   to reuse its typed research objects; no shared API contract,
   production scoring, auth, Arena routes, historical grades
   or data provider configuration is changed.

All output flags `source_independently_verified`,
`official_book_settlement_verified`, `scoring_eligible`
and `model_accuracy_established` remain hard-coded `False`.
The owner must authorize any future grading-semantic change or
production promotion. Close this draft PR to roll back.
