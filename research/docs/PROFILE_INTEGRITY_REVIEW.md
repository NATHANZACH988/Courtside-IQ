# Game-flow profile provenance guardrails

This review patch is based on the agency bridge PR #4 and changes no shared API contract or Arena scoring formula.

The profile aggregator now ignores non-final and duplicate game captures, only admits notes for banked final events and known same-team players, deduplicates repeated watcher notes, and quarantines the specifically retracted 401909840 bench-surge artifacts. Player keys use team-qualified display names to prevent immediate cross-team collisions; **stable athlete IDs remain necessary** before downstream joins.

This is **descriptive evidence only**, not a predictive model. A four-foul final box score does not prove a substitution was caused by fouls; same-position bench/starter surge correlation does not establish causation. Profiles are not permitted to modify pre-tip forecasts, frozen baselines or Arena scoring.

The default output path is repository-local; operators may set COURTSIDE_AGENCY_BASE to the agency workspace. The old hardcoded /home/hatch path is no longer required.

Validation: python -m unittest discover -s research/tests -p 'test_*.py' -v. Tests cover final-only ingestion, duplicate events, note provenance, retractions, name collisions and MM:SS minutes.

Outstanding gates: official data licensing/terms, stable ESPN athlete IDs, exact event time/source timestamps, 2026–27 season boundary enforcement, prospective holdout backtesting, roster-wide candidate coverage and five-game team bank before Play. Do not merge or promote this as production prediction authority without these gates.
