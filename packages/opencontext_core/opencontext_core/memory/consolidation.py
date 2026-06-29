"""Deterministic, rule-based consolidation for the agent memory store.

Two concerns live here:

* ``decide_action`` — at write time, classify an incoming record against the
  active records already sharing its key so the store can insert, no-op on an
  exact duplicate, update a near-duplicate in place, or supersede a conflicting
  belief. This keeps the store from accreting near-identical rows.
* ``summarize_records`` — off the hot path, distill a cluster of noisy records
  into one compact summary payload.

All decisions are deterministic: identical inputs always yield identical
outputs, with no model calls or randomness.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from opencontext_core.compat import StrEnum
from opencontext_core.models.agent_memory import MemoryLayer, MemoryRecord

# Above this token-overlap ratio two records are treated as the "same" belief
# expressed slightly differently and are merged rather than duplicated.
NEAR_DUPLICATE_THRESHOLD = 0.85

# Layers whose records are point-in-time beliefs: a new, distinct value for the
# same key replaces the old one. Event-log layers (working, episodic) instead
# accumulate and are compacted later by the background pass.
_BELIEF_LAYERS = frozenset({MemoryLayer.SEMANTIC, MemoryLayer.PROCEDURAL, MemoryLayer.FAILURE})

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class ConsolidationAction(StrEnum):
    """Outcome of classifying an incoming write against existing beliefs."""

    INSERT = "insert"
    NO_OP = "no_op"
    UPDATE = "update"
    SUPERSEDE = "supersede"


def _normalize(content: str) -> str:
    return " ".join(_TOKEN_RE.findall(content.lower()))


def _tokens(content: str) -> set[str]:
    return set(_TOKEN_RE.findall(content.lower()))


def jaccard(a: str, b: str) -> float:
    """Token Jaccard similarity of two strings in [0, 1]."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def decide_action(
    incoming: MemoryRecord,
    existing: list[MemoryRecord],
    *,
    near_duplicate_threshold: float = NEAR_DUPLICATE_THRESHOLD,
) -> tuple[ConsolidationAction, str | None]:
    """Decide how to fold ``incoming`` into the active records for its key.

    ``existing`` should already be filtered to the records sharing
    ``incoming.key`` (and, ideally, still valid). Returns the action plus the
    id of the related existing record (``None`` for INSERT).
    """
    candidates = [rec for rec in existing if rec.id != incoming.id and rec.key == incoming.key]
    if not candidates:
        return (ConsolidationAction.INSERT, None)

    incoming_norm = _normalize(incoming.content)

    # Exact (normalized) match -> nothing new to store.
    for rec in candidates:
        if _normalize(rec.content) == incoming_norm:
            return (ConsolidationAction.NO_OP, rec.id)

    # Near-duplicate -> refresh the existing record in place.
    best_id: str | None = None
    best_sim = 0.0
    for rec in candidates:
        sim = jaccard(rec.content, incoming.content)
        if sim > best_sim:
            best_sim = sim
            best_id = rec.id
    if best_id is not None and best_sim >= near_duplicate_threshold:
        return (ConsolidationAction.UPDATE, best_id)

    # Genuinely different content for the same key. For belief layers this is a
    # new value that replaces the prior one; for event-log layers it is a fresh
    # entry that should accumulate (compacted later by the background pass).
    if incoming.layer not in _BELIEF_LAYERS:
        return (ConsolidationAction.INSERT, None)
    most_confident = max(candidates, key=lambda r: r.confidence)
    return (ConsolidationAction.SUPERSEDE, most_confident.id)


# Composite-quality weights (PR-009 MEM-CONV memory quality score). Evidence and
# confidence dominate; reuse and freshness are secondary corroboration.
_QUALITY_WEIGHTS = {"evidence": 0.35, "reuse": 0.2, "freshness": 0.15, "confidence": 0.3}


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def memory_quality_score(record: MemoryRecord, *, now: datetime | None = None) -> float:
    """Composite per-record quality in [0, 1] (MEM-CONV memory quality score).

    Combines evidence (how many source refs back it), reuse (how often the belief
    has been refreshed), freshness (recency of last sighting), and confidence. A
    record with no evidence and never re-read scores low and is prune-eligible.
    """
    moment = now or datetime.now(tz=UTC)
    evidence = min(len(record.source_refs) / 2.0, 1.0)
    reuse = min(record.revision_count / 3.0, 1.0)
    seen = record.last_seen_at or record.updated_at
    age_days = max(0.0, (moment - _as_utc(seen)).days) if seen else 9999.0
    freshness = 1.0 / (1.0 + age_days / 30.0)
    confidence = record.confidence
    score = (
        _QUALITY_WEIGHTS["evidence"] * evidence
        + _QUALITY_WEIGHTS["reuse"] * reuse
        + _QUALITY_WEIGHTS["freshness"] * freshness
        + _QUALITY_WEIGHTS["confidence"] * confidence
    )
    return round(min(max(score, 0.0), 1.0), 4)


def summarize_records(records: list[MemoryRecord], *, max_items: int = 5) -> str:
    """Produce a compact, deterministic summary payload from a record cluster.

    The summary keeps the most confident, then most recent, representative lines
    so the distilled record is stable and human-readable.
    """
    ordered = sorted(records, key=lambda r: (r.confidence, r.created_at), reverse=True)
    seen: set[str] = set()
    lines: list[str] = []
    for rec in ordered:
        norm = _normalize(rec.content)
        if norm in seen:
            continue
        seen.add(norm)
        lines.append(rec.content.strip())
        if len(lines) >= max_items:
            break
    header = f"Consolidated {len(records)} records"
    body = "; ".join(lines)
    return f"{header}: {body}"
