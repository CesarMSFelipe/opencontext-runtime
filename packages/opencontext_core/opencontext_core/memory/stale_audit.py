"""Stale-memory audit (PR-009 MEM-CONV stale memory audit).

Lists records past their freshness/validity window with a reason and marks each
finding's record ``status = stale`` (book OC-MEMORY-001 §6 belief-validity axis).
Read-only by default: it reports findings; callers decide whether to persist the
status change or prune.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from opencontext_core.compat import UTC
from opencontext_core.memory.consolidation import jaccard, memory_quality_score
from opencontext_core.memory.contradictions import ContradictionDetector
from opencontext_core.models.agent_memory import MemoryRecord, MemoryStatus
from opencontext_core.policy.memory_content import forbidden_memory_content

# Defaults for the freshness/validity window.
_LOW_CONFIDENCE = 0.4
_MAX_AGE_DAYS = 90
_LOW_QUALITY = 0.3

# Token-Jaccard above which two same-key records are treated as near-duplicates.
_NEAR_DUPLICATE_THRESHOLD = 0.85


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


def _records(store: object, limit: int) -> list[MemoryRecord]:
    """Best-effort ``store.list_records`` — never raises; empty when unavailable."""
    lister = getattr(store, "list_records", None)
    if not callable(lister):
        return []
    try:
        return list(lister(limit=limit))
    except Exception:
        return []


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
    records = _records(store, limit)
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


def _group_by_key(records: list[MemoryRecord]) -> dict[str, list[MemoryRecord]]:
    groups: dict[str, list[MemoryRecord]] = {}
    for record in records:
        groups.setdefault(record.key, []).append(record)
    return groups


def _count_near_duplicates(records: list[MemoryRecord], threshold: float) -> int:
    """Count same-key record pairs whose content is a near-duplicate."""
    count = 0
    for group in _group_by_key(records).values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                if jaccard(group[i].content, group[j].content) >= threshold:
                    count += 1
    return count


def _count_conflicts(records: list[MemoryRecord]) -> int:
    """Count distinct same-key record pairs flagged as contradictory."""
    detector = ContradictionDetector()
    seen: set[frozenset[str]] = set()
    for group in _group_by_key(records).values():
        for i, record in enumerate(group):
            others = group[:i] + group[i + 1 :]
            for conflict in detector.detect(record, others):
                seen.add(frozenset({record.id, conflict.record_id}))
    return len(seen)


def audit_live_memory(
    store: object,
    *,
    now: datetime | None = None,
    limit: int = 1000,
    near_duplicate_threshold: float = _NEAR_DUPLICATE_THRESHOLD,
) -> dict[str, Any]:
    """Read-only audit of the live memory store (book §14 ``memory audit``).

    Operates on whatever ``store.list_records`` returns — the canonical
    AgentMemoryStore that ``memory list``/``memory doctor`` read — and reports
    record count, stale records (with a reason breakdown), near-duplicates,
    same-key conflicts, a composite quality score, and a chain-of-thought leak
    check. Never raises and never mutates: a store without ``list_records``
    audits as empty.
    """
    moment = now or datetime.now(tz=UTC)
    records = _records(store, limit)
    total = len(records)

    findings = stale_audit(store, now=moment, limit=limit)
    stale_reasons: dict[str, int] = {}
    for finding in findings:
        stale_reasons[finding.reason] = stale_reasons.get(finding.reason, 0) + 1

    if records:
        scores = [memory_quality_score(record, now=moment) for record in records]
        quality = {
            "average": round(sum(scores) / len(scores), 4),
            "minimum": round(min(scores), 4),
        }
    else:
        quality = {"average": 0.0, "minimum": 0.0}

    cot_leaks = sum(1 for record in records if forbidden_memory_content(record.content) is not None)

    return {
        "total": total,
        "stale": {"count": len(findings), "reasons": stale_reasons},
        "duplicates": _count_near_duplicates(records, near_duplicate_threshold),
        "conflicts": _count_conflicts(records),
        "quality": quality,
        "chain_of_thought_leaks": cot_leaks,
    }
