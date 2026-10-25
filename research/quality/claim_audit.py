"""Audit published research claims without accepting them as verified evidence.

Read-only and dependency-free. All digests, source times and licenses are
*assertions* until independently checked against underlying artifacts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import math
import re
import sys
from urllib.parse import urlsplit


_DIGEST = re.compile(r"^[a-fA-F0-9]{64}$")
_REV = re.compile(r"^[a-fA-F0-9]{40,64}$")
_KEY = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.:-]{2,100}$")
_KINDS = {"observational", "proxy_ticket", "actual_ticket", "prospective_forecast"}
_SCOPES = {"descriptive", "predictive", "profitability"}
_STATUSES = {"active", "superseded"}
_FRAMES = {"full_market_universe", "constructed_tickets", "published_winners", "other"}
_RIGHTS = {"unverified", "licensed", "restricted"}


@dataclass(frozen=True)
class ClaimAudit:
    structural_ready: bool
    independently_verified: bool
    scoring_eligible: bool
    reasons: tuple[str, ...]
    checked_claims: int


def _time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _id(value: object) -> bool:
    return isinstance(value, str) and _KEY.fullmatch(value) is not None


def _sha(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _url(value: object) -> bool:
    if not isinstance(value, str) or any(c.isspace() for c in value):
        return False
    try:
        url = urlsplit(value)
    except ValueError:
        return False
    return url.scheme == "https" and bool(url.hostname) and not url.username and not url.password


def _nonneg(value: object) -> bool:
    return type(value) is int and value >= 0


def audit_claims(document: object) -> ClaimAudit:
    """Reject missing provenance and silently revised/overstated findings.

    Structural success is *not* verification, licensing, or prediction accuracy.
    """
    reasons: list[str] = []
    if not isinstance(document, dict) or document.get("schema_version") != 1 or type(document.get("schema_version")) is not int:
        return ClaimAudit(False, False, False, ("unsupported_claim_manifest",), 0)
    claims = document.get("claims")
    if not isinstance(claims, list) or not claims:
        return ClaimAudit(False, False, False, ("claims_missing",), 0)
    ids: set[str] = set()
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    all_claims: dict[str, dict] = {}

    for index, claim in enumerate(claims):
        p = f"claim_{index}"
        if not isinstance(claim, dict):
            reasons.append(p + "_not_object")
            continue
        cid = claim.get("claim_id")
        if not _id(cid):
            reasons.append(p + "_id_invalid")
        elif cid in ids:
            reasons.append(p + "_id_duplicate")
        else:
            ids.add(cid)
            all_claims[cid] = claim
        kind = claim.get("kind")
        scope = claim.get("scope")
        if not isinstance(kind, str) or kind not in _KINDS:
            reasons.append(p + "_kind_invalid")
        if not isinstance(scope, str) or scope not in _SCOPES:
            reasons.append(p + "_scope_invalid")
        if not isinstance(claim.get("status"), str) or claim["status"] not in _STATUSES:
            reasons.append(p + "_status_invalid")
        for key in ("claim_key", "dataset_id", "cohort_id", "method_id"):
            if not _id(claim.get(key)):
                reasons.append(p + "_" + key + "_invalid")
        for key in ("dataset_sha256", "method_sha256"):
            if not _sha(claim.get(key)):
                reasons.append(p + "_" + key + "_missing")
        rev = claim.get("code_revision")
        if not isinstance(rev, str) or not _REV.fullmatch(rev):
            reasons.append(p + "_code_revision_missing")
        command = claim.get("reproduce_command")
        if not isinstance(command, str) or len(command.strip()) < 8:
            reasons.append(p + "_reproduction_missing")
        if not _url(claim.get("source_url")):
            reasons.append(p + "_source_url_invalid")
        rights = claim.get("rights_status")
        if not isinstance(rights, str) or rights not in _RIGHTS:
            reasons.append(p + "_rights_status_invalid")
        n = claim.get("numerator")
        d = claim.get("denominator")
        if not _nonneg(n) or not _nonneg(d) or d == 0 or n > d:
            reasons.append(p + "_fraction_invalid")
        frame = claim.get("sample_frame")
        if not isinstance(frame, str) or frame not in _FRAMES:
            reasons.append(p + "_sample_frame_invalid")
        if frame == "published_winners" and scope != "descriptive":
            reasons.append(p + "_winner_only_inference")
        if kind == "proxy_ticket" and scope == "profitability":
            reasons.append(p + "_proxy_cannot_establish_profitability")
        if kind == "proxy_ticket" and claim.get("line_kind") != "proxy":
            reasons.append(p + "_proxy_line_kind_missing")
        if kind == "actual_ticket":
            if claim.get("line_kind") != "posted":
                reasons.append(p + "_posted_line_missing")
            for key in ("book", "selection_side", "market_period", "settlement_version"):
                if not isinstance(claim.get(key), str) or not claim[key].strip():
                    reasons.append(p + "_" + key + "_missing")
            odds = claim.get("american_odds")
            if type(odds) is not int or (-100 < odds < 100):
                reasons.append(p + "_odds_invalid")
            line = claim.get("line")
            if (type(line) not in (int, float) or not math.isfinite(line)):
                reasons.append(p + "_line_missing_or_nonfinite")
            offered = _time(claim.get("quote_captured_at_utc"))
            start = _time(claim.get("event_start_utc"))
            if offered is None or start is None or offered >= start:
                reasons.append(p + "_quote_not_proven_pregame")
        if kind == "prospective_forecast" or scope == "predictive" or scope == "profitability":
            frozen = _time(claim.get("frozen_at_utc"))
            start = _time(claim.get("event_start_utc"))
            if frozen is None or start is None or frozen >= start:
                reasons.append(p + "_forecast_not_prefrozen")
            if not _sha(claim.get("frozen_artifact_sha256")):
                reasons.append(p + "_frozen_artifact_missing")
            if not _id(claim.get("evaluation_protocol_id")):
                reasons.append(p + "_evaluation_protocol_missing")
            protocol = _time(claim.get("protocol_frozen_at_utc"))
            if protocol is None or frozen is None or protocol > frozen:
                reasons.append(p + "_protocol_not_prefrozen")
            if not _nonneg(claim.get("holdout_events")) or claim["holdout_events"] == 0:
                reasons.append(p + "_holdout_missing")
        supersedes = claim.get("supersedes", [])
        if not isinstance(supersedes, list) or any(not _id(x) for x in supersedes):
            reasons.append(p + "_supersedes_invalid")
        elif cid in supersedes:
            reasons.append(p + "_self_supersession")
        if all(_id(claim.get(k)) for k in ("claim_key", "dataset_id", "cohort_id")):
            key = (claim["claim_key"], claim["dataset_id"], claim["cohort_id"])
            grouped.setdefault(key, []).append(claim)

    for cid, claim in all_claims.items():
        supersedes = claim.get("supersedes", [])
        if isinstance(supersedes, list):
            for old in supersedes:
                if not _id(old):
                    continue
                if old not in all_claims:
                    reasons.append(cid + "_unknown_superseded_claim")
                elif all_claims[old].get("status") != "superseded":
                    reasons.append(cid + "_superseded_claim_still_active")
    # A new number on the same dataset/cohort needs an explicit supersession,
    # not a silent edit. Different cohort IDs are not assumed equivalent.
    for group in grouped.values():
        valid = [x for x in group if _nonneg(x.get("numerator")) and _nonneg(x.get("denominator"))]
        for i, earlier in enumerate(valid):
            for later in valid[i + 1:]:
                if (earlier["numerator"], earlier["denominator"]) == (later["numerator"], later["denominator"]):
                    continue
                # Invalid supersession metadata must fail closed without
                # crashing the audit or being interpreted as an exception.
                later_links = later.get("supersedes", [])
                earlier_links = earlier.get("supersedes", [])
                if not isinstance(later_links, list):
                    later_links = []
                if not isinstance(earlier_links, list):
                    earlier_links = []
                if (earlier.get("claim_id") not in later_links
                        and later.get("claim_id") not in earlier_links):
                    reasons.append("unreconciled_cohort_result:" + str(earlier.get("claim_id")) + ":" + str(later.get("claim_id")))
    # Cyclic supersession would destroy the meaning of 'latest'.
    graph = {cid: [x for x in claim.get("supersedes", []) if _id(x) and x in all_claims]
             for cid, claim in all_claims.items()
             if isinstance(claim.get("supersedes", []), list)}
    # Iterative DFS avoids RecursionError on a large, untrusted chain.
    # Nodes in the active path indicate cycles; completed nodes are safe.
    visiting: set[str] = set()
    visited: set[str] = set()
    for root in graph:
        if root in visited:
            continue
        stack: list[tuple[str, bool]] = [(root, False)]
        while stack:
            node, leaving = stack.pop()
            if leaving:
                visiting.discard(node)
                visited.add(node)
                continue
            if node in visited:
                continue
            if node in visiting:
                reasons.append("supersession_cycle:" + node)
                continue
            visiting.add(node)
            stack.append((node, True))
            for nxt in reversed(graph.get(node, [])):
                if nxt in visiting:
                    reasons.append("supersession_cycle:" + nxt)
                elif nxt not in visited:
                    stack.append((nxt, False))

    return ClaimAudit(not reasons, False, False, tuple(reasons), len(claims))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m research.quality.claim_audit MANIFEST.json", file=sys.stderr)
        return 2
    try:
        document = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": "unreadable_manifest", "detail": str(exc)}))
        return 2
    result = audit_claims(document)
    print(json.dumps(result.__dict__, indent=2))
    return 0 if result.structural_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
