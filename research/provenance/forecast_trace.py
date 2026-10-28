"""Offline, research-only player-prop forecast provenance receipts.

A digest detects subsequent edits to a supplied record; it does NOT prove
that sources were authentic or the record existed before the event.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
from urllib.parse import urlparse

SCHEMA = "courtside-forecast-trace-v1"


def _unique_json_pairs(pairs: list[tuple[str, object]]) -> dict:
    """Reject ambiguous JSON objects instead of silently keeping the last key."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def load_strict_json(text: str) -> object:
    """Parse JSON without duplicate keys or nonstandard NaN/Infinity tokens."""
    return json.loads(text, object_pairs_hook=_unique_json_pairs,
                      parse_constant=_reject_json_constant)


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _time(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label}: timezone-aware ISO timestamp required")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label}: invalid ISO timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{label}: timezone required")
    return dt.astimezone(timezone.utc)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: nonempty text required")
    return value


def _url(value: object, label: str) -> str:
    url = _text(value, label)
    parts = urlparse(url)
    if parts.scheme != "https" or not parts.netloc or parts.username or parts.password:
        raise ValueError(f"{label}: https URL required")
    return url


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label}: finite numeric value required")
    return float(value)


def validate_trace(trace: dict) -> str:
    """Validate chronology and declared evidence; return canonical SHA-256.

    This checks the supplied universe only, not independent roster completeness,
    actual sportsbook availability, source rights, calibration, or bet quality.
    """
    if not isinstance(trace, dict) or trace.get("schema") != SCHEMA:
        raise ValueError("unsupported forecast trace schema")
    prompt = trace.get("prompt")
    if not isinstance(prompt, dict):
        raise ValueError("prompt object required")
    original = _text(prompt.get("text"), "original prompt")
    if prompt.get("sha256") != sha256(original.encode("utf-8")).hexdigest():
        raise ValueError("original prompt digest mismatch")
    model = trace.get("model")
    if not isinstance(model, dict):
        raise ValueError("model object required")
    for key in ("name", "version", "code_ref", "method"):
        _text(model.get(key), f"model.{key}")
    event = trace.get("event")
    if not isinstance(event, dict):
        raise ValueError("event object required")
    _text(event.get("id"), "event.id")
    tip = _time(event.get("tipoff_utc"), "event.tipoff_utc")
    created = _time(trace.get("created_at_utc"), "created_at_utc")
    frozen = _time(trace.get("frozen_at_utc"), "frozen_at_utc")
    if not created <= frozen < tip:
        raise ValueError("forecast must be created and frozen before tipoff")
    if trace.get("status") != "research_only":
        raise ValueError("research_only status required; no Play authority")

    sources = trace.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("nonempty source ledger required")
    source_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("source record must be an object")
        identity = _text(source.get("id"), "source.id")
        if identity in source_ids:
            raise ValueError("duplicate source id")
        source_ids.add(identity)
        _url(source.get("url"), "source.url")
        _text(source.get("input_or_claim"), "source.input_or_claim")
        retrieved = _time(source.get("retrieved_at_utc"), "source.retrieved_at_utc")
        if retrieved > frozen:
            raise ValueError("forecast source retrieved after freeze")
        digest = _text(source.get("sha256"), "source.sha256")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("source.sha256 must be lowercase SHA-256")

    candidates = trace.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("nonempty full candidate ledger required")
    keys: set[tuple[str, str]] = set()
    for row in candidates:
        if not isinstance(row, dict):
            raise ValueError("candidate must be an object")
        key = (_text(row.get("player_id"), "player_id"),
               _text(row.get("stat"), "stat"))
        if key in keys:
            raise ValueError("duplicate player-stat candidate")
        keys.add(key)
        _text(row.get("team_id"), "team_id")
        mean = _number(row.get("mean"), "mean")
        bounds = row.get("range")
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise ValueError("range must contain two endpoints")
        low, high = (_number(bounds[0], "range.low"), _number(bounds[1], "range.high"))
        if low < 0 or not low <= mean <= high:
            raise ValueError("range must contain the nonnegative mean")
        _text(row.get("calculation"), "calculation")
        refs = row.get("source_ids")
        if not isinstance(refs, list) or not refs or any(
                not isinstance(s, str) or s not in source_ids for s in refs):
            raise ValueError("candidate references unknown/missing source")
        if row.get("decision") not in {"consider", "reject", "unresolved"}:
            raise ValueError("candidate decision invalid")
        _text(row.get("reason"), "candidate.reason")

    quotes = trace.get("quotes")
    if not isinstance(quotes, list):
        raise ValueError("quotes list required (can be empty)")
    quote_ids: set[str] = set()
    for quote in quotes:
        if not isinstance(quote, dict):
            raise ValueError("quote must be an object")
        identity = _text(quote.get("id"), "quote.id")
        if identity in quote_ids:
            raise ValueError("duplicate quote id")
        quote_ids.add(identity)
        if (quote.get("player_id"), quote.get("stat")) not in keys:
            raise ValueError("quote references unknown candidate")
        _text(quote.get("sportsbook"), "quote.sportsbook")
        _url(quote.get("url"), "quote.url")
        if quote.get("kind") not in {"over", "under", "alternate", "exact", "range"}:
            raise ValueError("quote.kind invalid")
        odds = quote.get("american_odds")
        if isinstance(odds, bool) or not isinstance(odds, int) or -100 < odds < 100:
            raise ValueError("quote.american_odds invalid")
        low = _number(quote.get("lower"), "quote.lower")
        high = _number(quote.get("upper"), "quote.upper")
        if low < 0 or low > high or (quote.get("kind") == "exact" and low != high):
            raise ValueError("quote bounds invalid")
        if not frozen <= _time(quote.get("retrieved_at_utc"), "quote.retrieved_at_utc") < tip:
            raise ValueError("quote must be captured after projection freeze and before tip")
    return _digest(trace)


def seal_trace(trace: dict, *, now: datetime | None = None) -> dict:
    """Seal a trace before tip. A local seal is NOT an external timestamp."""
    digest = validate_trace(trace)
    at = now if now is not None else datetime.now(timezone.utc)
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("seal time must be timezone aware")
    at = at.astimezone(timezone.utc)
    if at >= _time(trace["event"]["tipoff_utc"], "tipoff"):
        raise ValueError("cannot seal after tipoff")
    if at < _time(trace["frozen_at_utc"], "frozen"):
        raise ValueError("cannot seal before projection freeze")
    if any(_time(q["retrieved_at_utc"], "quote") > at for q in trace["quotes"]):
        raise ValueError("cannot seal before supplied market capture")
    sealed_at = at.isoformat()
    return {"trace": trace, "trace_sha256": digest,
            "sealed_at_utc": sealed_at,
            "seal_sha256": _digest({"trace_sha256": digest, "sealed_at_utc": sealed_at}),
            "external_timestamp_verified": False}


def verify_receipt(receipt: dict) -> str:
    if not isinstance(receipt, dict) or not isinstance(receipt.get("trace"), dict):
        raise ValueError("invalid receipt")
    digest = validate_trace(receipt["trace"])
    if receipt.get("trace_sha256") != digest:
        raise ValueError("sealed trace content changed")
    sealed = _time(receipt.get("sealed_at_utc"), "sealed_at_utc")
    expected_seal = _digest({"trace_sha256": digest,
                             "sealed_at_utc": receipt["sealed_at_utc"]})
    if receipt.get("seal_sha256") != expected_seal:
        raise ValueError("seal metadata changed")
    if not _time(receipt["trace"]["frozen_at_utc"], "freeze") <= sealed < _time(
            receipt["trace"]["event"]["tipoff_utc"], "tipoff"):
        raise ValueError("seal chronology invalid")
    if any(_time(q["retrieved_at_utc"], "quote") > sealed for q in receipt["trace"]["quotes"]):
        raise ValueError("quote timestamp after seal")
    if receipt.get("external_timestamp_verified") is not False:
        raise ValueError("self-issued receipt cannot assert external verification")
    return digest


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "verify"))
    parser.add_argument("input", type=Path)
    parser.add_argument("output", nargs="?", type=Path)
    args = parser.parse_args()
    data = load_strict_json(args.input.read_text(encoding="utf-8"))
    if args.command == "freeze":
        if args.output is None:
            parser.error("freeze requires output path")
        receipt = seal_trace(data)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        print(receipt["trace_sha256"])
    else:
        print(verify_receipt(data))


if __name__ == "__main__":
    main()
