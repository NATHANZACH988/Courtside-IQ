# Full-Roster Prop Screening

Owner ruling: Analyze every rostered player on both teams of every eligible game before choosing any props. Do not preselect famous players or copy editorial picks.

Pipeline: (1) full game-day roster and status coverage; (2) injury, rotation, foul, coaching and minute scenarios for starters and bench; (3) per-player per-stat opportunity distributions including teammate/opponent correlations; (4) independent timestamped market comparison after projections; (5) evidence gates and ranking across the entire candidate universe; (6) select zero to five qualified candidates, retaining all rejected candidates and reasons.

Required outputs: game-scoped player_universe with roster and availability provenance; candidate_ledger for every eligible player-stat combination with projection, uncertainty, data coverage, gate status and rejection reason; full player coverage counts and source timestamps.

Safety: No Play designation until five current-season banked games per team unless explicit owner override. No fabricated lines, probabilities, or live stats. Frozen forecasts never change after tipoff. Unknown availability is flagged, not silently excluded.

Acceptance tests: starters and bench represented; out/questionable statuses handled; team minutes reconcile; foul-out substitution effects propagate; deterministic rankings from same snapshot; zero candidates allowed; no sportsbook input influencing independent model projections; complete rejection ledger.

Status: specification only, implementation pending.
