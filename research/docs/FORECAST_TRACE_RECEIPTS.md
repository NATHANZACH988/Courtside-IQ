# Forecast trace receipts — independent research experiment

The original Oct 27 reference numbers (7.0, 8.0, 12.0, 9.9, 20.0, etc.) have **unresolved provenance**. Do not attribute them to a publisher, a verified Courtside IQ model, or winning sportsbook picks. This add-only research tool preserves a repeatable trail for future forecasts. It does **not** reconstruct the missing original calculation or establish predictive accuracy.

## Mandatory record before tip

Use `research/provenance/forecast_trace.py` with a JSON object matching `courtside-forecast-trace-v1`. Record the **literal original prompt** and its UTF-8 SHA-256, the model name/version/code reference/method, event ID and scheduled UTC tip, created and independent projection-freeze times, all source URLs and retrieval times, source content SHA-256 and what each source supplied, **all** player-stat candidates (including rejects and unresolved), numerical mean and plausible range, source IDs and the actual calculation, plus optional real sportsbook quotes. For quotes include the bookmaker, URL, exact/alternate/over/under/range market type, bounds, American odds and captured time. An empty quote list is valid and is **not** a betting result. Use source hashes of actually retained source material, not invented digests.

Record pregame probability distributions, minutes scenarios, injury revisions, game-bank eligibility, team/roster coverage, and selection/rejection reasons in additional evidence fields as needed. The validator checks the **declared** player-stat universe, not whether the universe contains every player. The independent full-roster, five-current-season-game, injury, market and price gates still apply. A mean and range do **not** imply a probability for exact points or a three-point band. Do not calculate expected value without an actual probability distribution and sportsbook price.

## Example commands

```bash
python research/provenance/forecast_trace.py freeze research/experiments/2026-10-28/raw.json research/experiments/2026-10-28/frozen.json
python research/provenance/forecast_trace.py verify research/experiments/2026-10-28/frozen.json
python -m unittest discover -s research/tests -p 'test_*.py' -v
```

`freeze` and `verify` reject duplicate JSON object keys (including nested candidate/quote values) and nonstandard `NaN`/`Infinity` tokens before any digest or chronology checks. Without this guard, two parsers could interpret a receipt differently while one silently retains the last duplicate key.

`freeze` creates the output exclusively (refuses overwrite), checks that sources predate forecast freeze, market captures occur after the independent projection freeze, and the receipt is sealed before tipoff. It records a deterministic SHA-256 of the complete trace and of its seal metadata. `verify` detects changes **relative to the supplied receipt**. Do not edit the frozen receipt to add results: store official final stats, sportsbook settlements, push rules, and graded errors in a separate postgame file referencing `trace_sha256` and the original quote IDs.

## Critical integrity limitations

A self-issued timestamp or content hash is **not proof of when a prediction was originally made**; the file and its hashes can be forged together. Publish or commit a receipt before tipoff to an independently timestamped, append-only archive, and retain source snapshots only when license/terms permit. This tool does not fetch providers, independently authenticate ESPN or sportsbook content, verify availability of quoted markets, validate source licensing, compute odds/probabilities, perform roster reconciliation, grade predictions, or authorize Plays. Synthetic tests exercise data validation only. The shared API contract, production scoring, authentication and historical grades are untouched.
