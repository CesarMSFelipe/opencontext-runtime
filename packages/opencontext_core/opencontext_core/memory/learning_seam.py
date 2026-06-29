"""Learning-loop integration seam (PR-009 MEM-CONV; consumed by PR-000.4).

Durable memory produced by a run feeds the learning loop so prior knowledge can
bias future runs. This module is the *seam*: it turns durable ``MemoryRecord``s
into learning candidates and pushes a non-blocking memory outcome into the
learning orchestrator via ``learning.feed.record_outcome``. The consumer that
acts on these candidates ships in PR-000.4; surfacing prior records at retrieval
time is already provided by ``memory.retrieval`` + the planner failure-boost.

Memory stays decoupled: the orchestrator is passed in (``Any``), and the learning
import is lazy and best-effort so a missing/failing learning subsystem never
breaks a memory write.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opencontext_core.models.agent_memory import MemoryLayer, MemoryRecord


@dataclass(frozen=True)
class MemoryLearningCandidate:
    """A durable memory item offered to the learning loop."""

    record_id: str
    layer: str
    content: str
    task: str
    is_failure: bool


def build_learning_candidates(
    records: list[MemoryRecord], *, task: str
) -> list[MemoryLearningCandidate]:
    """Project durable records into learning candidates (failures highlighted)."""
    candidates: list[MemoryLearningCandidate] = []
    for record in records:
        candidates.append(
            MemoryLearningCandidate(
                record_id=record.id,
                layer=record.layer.value,
                content=record.content,
                task=task,
                is_failure=record.layer
                in (MemoryLayer.FAILURE, MemoryLayer.HARNESS_EXPERIENCE),
            )
        )
    return candidates


def feed_memory_outcome(
    orchestrator: Any | None,
    *,
    task: str,
    records: list[MemoryRecord],
    success: bool | None = None,
) -> list[MemoryLearningCandidate]:
    """Push a memory outcome into the learning loop (non-blocking).

    Returns the learning candidates regardless of whether the orchestrator is
    present, so callers can inspect/forward them even with learning disabled.
    """
    candidates = build_learning_candidates(records, task=task)
    if orchestrator is None or not candidates:
        return candidates
    try:
        from opencontext_core.learning.feed import record_outcome

        record_outcome(
            orchestrator,
            operation_type="memory_harvest",
            query=task,
            task_type="memory",
            success=success,
            metadata={
                "durable_memories": len(candidates),
                "failure_memories": sum(1 for c in candidates if c.is_failure),
            },
        )
    except Exception:
        return candidates
    return candidates
