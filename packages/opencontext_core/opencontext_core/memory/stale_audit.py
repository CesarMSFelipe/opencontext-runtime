"""Stale-memory audit (PR-009 MEM-CONV stale memory audit).

Lists records past their freshness/validity window with a reason and marks each
finding's record ``status = stale`` (book OC-MEMORY-001 §6 belief-validity axis).
Read-only by default: it reports findings; callers decide whether to persist the
status change or prune.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from opencontext_core.compat import UTC
from opencontext_core.memory.consolidation import memory_quality_score
from opencontext_core.models.agent_memory import MemoryRecord, MemoryStatus

# Defaults for the freshness/validity window.
_LOW_CONFIDENCE = 0.4
_MAX_AGE_DAYS = 90
_LOW_QUALITY = 0.3


@dataclass(frozen=True)
class StaleFinding:
    """One stale record plus the reason it was flagged."""

    record: MemoryRecord
    reason: str


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _stale_reason(
    record: MemoryRecord,
    *,
    now: datetime,
    low_confidence: float,
    max_age_days: int,
    low_quality: float,
) -> str | None:
    if record.invalid_at is not None or record.superseded_by is not None:
        return "invalidated"
    if record.contradicted_by and record.confidence < low_confidence:
        return "contradicted_low_confidence"
    seen = record.last_seen_at or record.updated_at
    age_days = (now - _as_utc(seen)).days if seen else max_age_days + 1
    if age_days > max_age_days and record.confidence < low_confidence:
        return "aged_low_confidence"
    if memory_quality_score(record, now=now) < low_quality and record.confidence < low_confidence:
        return "low_quality"
    return None


def stale_audit(
    store: object,
    *,
    now: datetime | None = None,
    limit: int = 1000,
    low_confidence: float = _LOW_CONFIDENCE,
    max_age_days: int = _MAX_AGE_DAYS,
    low_quality: float = _LOW_QUALITY,
) -> list[StaleFinding]:
    """Return stale records (status forced to ``stale``) with a reason each."""
    moment = now or datetime.now(tz=UTC)
    lister = getattr(store, "list_records", None)
    records: list[MemoryRecord] = []
    if callable(lister):
        try:
            records = list(lister(limit=limit))
        except Exception:
            records = []
    findings: list[StaleFinding] = []
    for record in records:
        reason = _stale_reason(
            record,
            now=moment,
            low_confidence=low_confidence,
            max_age_days=max_age_days,
            low_quality=low_quality,
        )
        if reason is not None:
            flagged = record.model_copy(update={"status": MemoryStatus.STALE})
            findings.append(StaleFinding(record=flagged, reason=reason))
    return findings
