"""Source-attributed evidence records — never fabricate live data."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class EvidenceRecord:
    claim: str
    source_url: str
    observed_at_utc: str
    verification: str  # verified | assumed | inferred
    payload: dict[str, Any]

    def to_dict(self) -> dict:
        return asdict(self)


def require_source(source_url: str | None) -> str:
    if not source_url or not str(source_url).strip():
        raise ValueError("source_url required — do not invent statistics")
    return str(source_url).strip()
