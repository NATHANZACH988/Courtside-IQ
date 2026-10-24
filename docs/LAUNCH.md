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

## Security gates (required before any hosted beta)

The current identity system is **not suitable for public access**. Demo login
uses only a display name and can impersonate existing accounts. It is disabled
by default at the HTTP boundary. For a local, trusted demonstration only, set
`COURTSIDE_IQ_ALLOW_INSECURE_DEMO_LOGIN=1` and access the server from
127.0.0.1 or ::1. Never enable this on an internet-facing service; replace
it with authenticated invite-based accounts and session management first.

The state-changing lock job is **POST /api/admin/lock-due** (GET no longer
changes state). It requires the `X-Courtside-IQ-Admin-Token` header matching
a configured `COURTSIDE_IQ_ADMIN_TOKEN` of at least 32 characters.
Store the secret outside source control, use HTTPS in hosted environments,
and rotate it if exposed. With no valid secret, the endpoint fails closed.
Cron should use POST with this header, not GET. This is a temporary
internal-only control, not a substitute for full administrative authorization.

Example for local testing (do not copy a real secret into logs or the repo):

```bash
export COURTSIDE_IQ_ALLOW_INSECURE_DEMO_LOGIN=1
export COURTSIDE_IQ_ADMIN_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python -m arena.api
```

These safeguards do **not** certify the app for public deployment. Authentication,
TLS, rate limits, input bounds, session storage, authorized settlement, source
rights and prediction integrity remain release gates.
