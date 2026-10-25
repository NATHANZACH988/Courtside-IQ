# Historical market-quote readiness audit

**Status:** research-only, read-only. This is layered on the draft multi-sport
evidence ledger and does not change the shared API contract or NBA scoring.

The existing historical `MarketQuote` stores athlete, market, line, price,
sportsbook, and source timestamps, but **not which side was selected**, the
market period, or the applicable settlement rules. A price without a side
cannot establish a winning ticket, a hit rate, a bet return, or a model edge.

Use `research.core.market_audit.audit_quote(event, quote, as_of)` to obtain
an immutable readiness report. It checks event/team identity, sport-market
taxonomy, pregame chronology, point-in-time publication/capture, and presence
of a declared raw-payload SHA-256. The digest is **not** independently verified
against raw bytes by this audit.

The `point_in_time_replay_ready` result is strictly a structural signal.
Even when true, `scoring_eligible` and `settlement_eligible` remain false,
and `rights_review_required` remains true. A `rights='licensed'` string is
not proof of legal entitlement. Data ingestion and actual authorization checks
must be implemented separately.

Run: `python -m unittest discover -s research/tests -p 'test_*.py' -v`

**Next independent work:** source-rights audit; immutable raw capture storage;
side/period/settlement schema proposal requiring owner review; original-line
and loss-inclusive historical market universe; walk-forward grading. Do not
infer winning-ticket results from odds or observed player stats alone.
