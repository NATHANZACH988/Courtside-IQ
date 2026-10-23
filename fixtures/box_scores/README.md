# Offline box-score fixtures

These fixtures are **source-attributed snapshots** for repeatable automated tests.
They are not live NBA feeds. Each file records:

- `source_url` — public page or API document used when the snapshot was taken
- `fetched_at_utc` — when the snapshot was captured
- `note` — that values are frozen for tests

Live ingestion tests must skip with a reason when a live source is unreachable.
Never invent statistics and present them as live results.
