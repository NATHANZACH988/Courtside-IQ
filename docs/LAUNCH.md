# Launch notes (private beta)

## Run locally

```bash
python -m arena.api
# or
python -c "from arena.api import serve; serve()"
```

Open http://127.0.0.1:8080 — mobile-first Prediction Arena UI.

## Tests

```bash
PYTHONPATH=. python -m unittest discover -s research/tests -p 'test_*.py' -v
PYTHONPATH=. python -m unittest discover -s arena/tests -p 'test_*.py' -v
PYTHONPATH=. python -m unittest discover -s tests -p 'test_*.py' -v
```

## Budget posture

Prefer free-tier SQLite + a single small VM or static+serverless host within the
$50 initial budget. Do not commit paid infrastructure without owner approval.
Verify commercial-use terms for any live NBA data source before deployment.
