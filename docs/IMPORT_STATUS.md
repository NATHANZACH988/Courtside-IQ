# Starter import status

Source: `courtside-iq-dual-agent-starter(1).zip` (34 files, ZIP integrity verified locally by prior agent).

## GitHub / this environment

| Item | Status |
|------|--------|
| Collaboration foundation (`README`, docs, CI) | Present on `main` |
| Starter ZIP in this Cloud Agent workspace | **Not found** |
| Starter ZIP on GitHub releases/contents | **Not present** |
| Research + Arena + web implementation | **Scaffolded by Cursor** on branch `cursor/prediction-vertical-slice-f5e3` (not the original ZIP) |

**Imported from ZIP:** none (archive unavailable in this environment).

**Created instead (Cursor vertical slice):**

- `arena/` — Prediction Arena domain service, SQLite schema, closeness-v1 scoring, stdlib HTTP API
- `research/` — doctrine gates, foul-trouble, hot/cold streaks, minutes helpers, evidence records
- `web/` — mobile-first league homepage prototype
- `fixtures/box_scores/` — source-attributed offline box-score fixture
- `docs/SCHEMA_PROPOSAL.md`, `docs/SCORING_V1.md`, `docs/LAUNCH.md`
- Tests under `arena/tests`, `research/tests`, `tests`

When the ZIP becomes available, import with the commands below **without overwriting**
`README.md`, `docs/API_CONTRACT.md`, `docs/GROK_TASK_BRIEF.md`, `docs/AGENT_COLLABORATION.md`,
or Cursor’s newer Arena modules without review:

```bash
unzip 'courtside-iq-dual-agent-starter(1).zip' -d /tmp/courtside-import
cd /path/to/clone/of/Courtside-IQ
# Diff carefully before copying — research/ and web/ already exist.
cp -R /tmp/courtside-import/courtside-iq/research ./research-from-zip
cp -R /tmp/courtside-import/courtside-iq/web ./web-from-zip
cp -R /tmp/courtside-import/courtside-iq/tests ./tests-from-zip
# Merge selectively after review.
```

Do not treat documentation alone as evidence of deployment.
