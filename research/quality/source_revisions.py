"""Sport-neutral, append-only research source revision and disagreement ledger.

This is a research-only in-memory ledger, not a provider crawler, live injury
feed, timestamp attestation, identity crosswalk, prediction or scoring system.
All timestamps, source URLs, rights labels and payload digests are *claims*
until independently validated against the original raw artifacts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
import re
from urllib.parse import parse_qsl, urlsplit


_ID = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]*:[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
_METRIC = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_SPORT = re.compile(r"^[A-Z][A-Z0-9_]{1,19}$")
_SHA = re.compile(r"^[a-fA-F0-9]{64}$")
_RIGHTS = frozenset({"unverified", "restricted", "licensed"})
_STATES = frozenset({"active", "withdrawn"})
_SECRET_KEYS = frozenset({
    "apikey", "api_key", "access_token", "token", "auth", "password",
    "secret", "key", "client_secret", "authorization", "signature",
})


def _require_id(value: object, field: str) -> None:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError(f"{field} must be a provider-qualified stable ID")


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _source_url(value: object) -> None:
    if not isinstance(value, str) or any(c.isspace() for c in value):
        raise ValueError("source_url must be a credential-free HTTPS URL")
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.fragment):
            raise ValueError("source_url must be a credential-free HTTPS URL")
        # A valid hostname alone cannot establish trustworthy provenance.
        if any(k.casefold() in _SECRET_KEYS for k, _ in
               parse_qsl(parsed.query, keep_blank_values=True)):
            raise ValueError("source_url cannot contain credentials in query parameters")
    except ValueError as exc:
        raise ValueError("source_url must be a credential-free HTTPS URL") from exc


def _fact(value: object, state: str) -> None:
    if state == "withdrawn":
        if value is not None:
            raise ValueError("withdrawn revisions cannot contain an active fact")
        return
    if type(value) is str:
        if not value.strip() or len(value) > 2000:
            raise ValueError("active string facts must be nonblank and <= 2000 characters")
    elif type(value) is int:
        if abs(value) > 1_000_000_000:
            raise ValueError("active numeric facts must be bounded")
    elif type(value) is float:
        if not isfinite(value) or abs(value) > 1_000_000_000:
            raise ValueError("active numeric facts must be finite and bounded")
    else:
        raise ValueError("active facts must be text or a finite numeric value")


def _value_key(value: str | int | float | None) -> tuple[str, object]:
    """Compare 12 with 12.0 as equivalent, but not '12' with 12."""
    if type(value) in (int, float):
        return ("number", float(value))
    return ("string", value)


@dataclass(frozen=True)
class EventClock:
    sport: str
    event_id: str
    scheduled_start: datetime
    home_team_id: str
    away_team_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.sport, str) or _SPORT.fullmatch(self.sport) is None:
            raise ValueError("sport must be an uppercase sport code")
        _require_id(self.event_id, "event_id")
        if not self.event_id.startswith(self.sport.lower() + ":"):
            raise ValueError("event_id must be sport-scoped")
        _require_id(self.home_team_id, "home_team_id")
        _require_id(self.away_team_id, "away_team_id")
        if self.home_team_id == self.away_team_id:
            raise ValueError("home and away teams must differ")
        object.__setattr__(self, "scheduled_start",
                           _utc(self.scheduled_start, "scheduled_start"))


@dataclass(frozen=True)
class SourceRevision:
    revision_id: str
    series_id: str
    sport: str
    event_id: str
    entity_id: str
    metric: str
    provider: str
    state: str
    value: str | int | float | None
    source_url: str
    published_at: datetime
    captured_at: datetime
    effective_at: datetime
    raw_sha256: str
    rights_status: str = "unverified"
    team_id: str | None = None
    supersedes: str | None = None

    def __post_init__(self) -> None:
        for field in ("revision_id", "series_id", "event_id", "entity_id"):
            _require_id(getattr(self, field), field)
        if self.team_id is not None:
            _require_id(self.team_id, "team_id")
        if self.supersedes is not None:
            _require_id(self.supersedes, "supersedes")
        if not isinstance(self.sport, str) or _SPORT.fullmatch(self.sport) is None:
            raise ValueError("invalid sport")
        if not self.event_id.startswith(self.sport.lower() + ":"):
            raise ValueError("event_id must be sport-scoped")
        if not isinstance(self.metric, str) or _METRIC.fullmatch(self.metric) is None:
            raise ValueError("metric must be a lowercase stable key")
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("provider is required")
        if not isinstance(self.state, str) or self.state not in _STATES:
            raise ValueError("state must be active or withdrawn")
        _fact(self.value, self.state)
        _source_url(self.source_url)
        if not isinstance(self.raw_sha256, str) or _SHA.fullmatch(self.raw_sha256) is None:
            raise ValueError("raw_sha256 must be 64 hexadecimal characters")
        if not isinstance(self.rights_status, str) or self.rights_status not in _RIGHTS:
            raise ValueError("rights_status must be unverified, restricted, or licensed")
        published = _utc(self.published_at, "published_at")
        captured = _utc(self.captured_at, "captured_at")
        effective = _utc(self.effective_at, "effective_at")
        if published > captured:
            raise ValueError("source cannot be captured before source publication")
        object.__setattr__(self, "published_at", published)
        object.__setattr__(self, "captured_at", captured)
        object.__setattr__(self, "effective_at", effective)


@dataclass(frozen=True)
class Disagreement:
    event_id: str
    entity_id: str
    metric: str
    revision_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceView:
    event_id: str
    as_of: datetime
    active_revisions: tuple[SourceRevision, ...]
    withdrawn_series: tuple[str, ...]
    disagreements: tuple[Disagreement, ...]
    team_disagreements: tuple[tuple[str, tuple[str, ...]], ...]
    stale_revision_ids: tuple[str, ...]
    rights_review_revision_ids: tuple[str, ...]
    provenance_independently_verified: bool = False
    scoring_eligible: bool = False


class SourceRevisionLedger:
    """Append-only, event-scoped source history with as-of reconstruction.

    The ledger checks *structural* chronology. It does not authenticate a
    source or confirm a stated data license. No filesystem/network side effects.
    """

    def __init__(self) -> None:
        self._events: dict[str, EventClock] = {}
        self._revisions: dict[str, SourceRevision] = {}
        self._series: dict[str, list[str]] = {}
        # Disallow duplicate provider/metric series that would masquerade
        # as independent corroboration of the exact same feed.
        self._provider_keys: dict[tuple[str, str, str, str], str] = {}

    def add_event(self, event: EventClock) -> None:
        if not isinstance(event, EventClock):
            raise TypeError("expected EventClock")
        if event.event_id in self._events:
            raise ValueError("duplicate event_id")
        self._events[event.event_id] = event

    def add_revision(self, revision: SourceRevision) -> None:
        if not isinstance(revision, SourceRevision):
            raise TypeError("expected SourceRevision")
        event = self._events.get(revision.event_id)
        if event is None:
            raise ValueError("revision event is not registered")
        if revision.sport != event.sport:
            raise ValueError("sport mismatch for event")
        if revision.team_id is not None and revision.team_id not in (
                event.home_team_id, event.away_team_id):
            raise ValueError("team_id is not part of event")
        if revision.revision_id in self._revisions:
            raise ValueError("duplicate revision_id")

        provider_key = (revision.event_id, revision.entity_id,
                        revision.metric, revision.provider.casefold())
        assigned_series = self._provider_keys.get(provider_key)
        if assigned_series is not None and assigned_series != revision.series_id:
            raise ValueError("provider/entity/metric already has a series")

        history = self._series.get(revision.series_id, [])
        if history:
            previous = self._revisions[history[-1]]
            if (revision.sport != previous.sport or
                    revision.event_id != previous.event_id or
                    revision.entity_id != previous.entity_id or
                    revision.metric != previous.metric or
                    revision.provider.casefold() != previous.provider.casefold()):
                raise ValueError("revision series identity mismatch")
            if revision.supersedes != previous.revision_id:
                raise ValueError("revision must supersede latest known version")
            if revision.captured_at <= previous.captured_at:
                raise ValueError("revision capture must follow predecessor capture")
            if revision.raw_sha256 == previous.raw_sha256:
                raise ValueError("identical source payload cannot claim a new revision")
        elif revision.supersedes is not None:
            raise ValueError("first revision cannot supersede another revision")

        self._revisions[revision.revision_id] = revision
        self._series.setdefault(revision.series_id, []).append(revision.revision_id)
        self._provider_keys[provider_key] = revision.series_id

    def history(self, series_id: str) -> tuple[SourceRevision, ...]:
        _require_id(series_id, "series_id")
        return tuple(self._revisions[rid] for rid in self._series.get(series_id, []))

    def as_of(self, event_id: str, cutoff: datetime, *,
              pregame: bool = True, max_age_seconds: int | None = None) -> EvidenceView:
        event = self._events.get(event_id)
        if event is None:
            raise ValueError("event is not registered")
        stamp = _utc(cutoff, "cutoff")
        if pregame and stamp >= event.scheduled_start:
            raise ValueError("pregame cutoff must precede scheduled start")
        if max_age_seconds is not None and (
                type(max_age_seconds) is not int or max_age_seconds < 0):
            raise ValueError("max_age_seconds must be a nonnegative integer")

        latest: list[SourceRevision] = []
        for ids in self._series.values():
            eligible = [
                self._revisions[rid] for rid in ids
                if self._revisions[rid].event_id == event_id
                and self._revisions[rid].published_at <= stamp
                and self._revisions[rid].captured_at <= stamp
            ]
            if eligible:
                latest.append(eligible[-1])
        active = sorted((r for r in latest if r.state == "active"),
                        key=lambda r: r.revision_id)
        withdrawn = tuple(sorted(r.series_id for r in latest if r.state == "withdrawn"))

        by_fact: dict[tuple[str, str], list[SourceRevision]] = {}
        teams: dict[str, set[str]] = {}
        for revision in active:
            by_fact.setdefault((revision.entity_id, revision.metric), []).append(revision)
            if revision.team_id is not None:
                teams.setdefault(revision.entity_id, set()).add(revision.team_id)
        disagreements = []
        for (entity_id, metric), records in sorted(by_fact.items()):
            if len({_value_key(r.value) for r in records}) > 1:
                disagreements.append(Disagreement(
                    event_id, entity_id, metric,
                    tuple(sorted(r.revision_id for r in records))))
        team_disagreements = tuple(
            (eid, tuple(sorted(team_ids)))
            for eid, team_ids in sorted(teams.items()) if len(team_ids) > 1
        )
        stale = tuple(sorted(
            r.revision_id for r in active
            if max_age_seconds is not None
            and (stamp - r.captured_at).total_seconds() > max_age_seconds
        ))
        # Even 'licensed' is a label, not externally verified permission.
        unverified = tuple(sorted(
            r.revision_id for r in active if r.rights_status != "licensed"))
        return EvidenceView(
            event_id=event_id, as_of=stamp,
            active_revisions=tuple(active),
            withdrawn_series=withdrawn,
            disagreements=tuple(disagreements),
            team_disagreements=team_disagreements,
            stale_revision_ids=stale,
            rights_review_revision_ids=unverified,
        )
