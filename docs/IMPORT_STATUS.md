# Starter import status

Source: `courtside-iq-dual-agent-starter(1).zip` (34 files, ZIP integrity verified locally by prior agent).

## GitHub / this environment

| Item | Status |
|------|--------|
| Collaboration foundation (`README`, docs, CI) | Present on `main` |
| Sideline / game-flow research specs | Present on `main` (`docs/SIDELINE_COACHING_INTELLIGENCE.md`, `docs/GAME_FLOW_INTELLIGENCE.md`) |
| Starter ZIP in this Cloud Agent workspace | **Not found** |
| Starter ZIP on GitHub releases/contents | **Not present** |
| Cursor Arena + research scaffold | On `cursor/prediction-vertical-slice-f5e3` |

**Imported from ZIP:** none (archive still unavailable). Owner action requested to upload/push the ZIP.

**Built without ZIP (Cursor):**

- Prediction Arena vertical slice with tipoff locks + closeness-v1 grading
- Live ESPN capture path + CHI@MIL 2026-10-23 final fixture (`fixtures/box_scores/live_captures/401909848.json`)
- Coaching intelligence schemas + PBP foul/sub/hot-cold extractors + rotation frequency baseline
- Mobile league UI + tonight board + coaching insight panel

When the ZIP arrives, import into side folders first, then merge selectively:

```bash
unzip 'courtside-iq-dual-agent-starter(1).zip' -d /tmp/courtside-import
cp -R /tmp/courtside-import/courtside-iq/research ./research-from-zip
cp -R /tmp/courtside-import/courtside-iq/web ./web-from-zip
cp -R /tmp/courtside-import/courtside-iq/tests ./tests-from-zip
# Diff/merge carefully — do not overwrite shared collaboration docs blindly.
```
