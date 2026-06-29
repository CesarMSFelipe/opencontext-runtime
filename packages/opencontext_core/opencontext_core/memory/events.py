"""Named memory lifecycle events (book OC-MEMORY-001 §24).

All event types belong to the ``memory`` event family (doc 59 — event hierarchy)
so they slot into the runtime timeline (``runtime.events.EventCategory.memory``).
This module provides the named constants plus a minimal, dependency-free emitter
hook: the Memory Harness and retrieval path emit through a ``MemoryEventEmitter``;
callers/tests subscribe a sink to observe the stream without standing up the full
``RuntimeEvent`` bus (which requires a session id).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from opencontext_core.compat import UTC, StrEnum


class MemoryEvent(StrEnum):
    """Named memory events (dotted, ``memory.*`` family)."""

    CANDIDATE_CREATED = "memory.candidate.created"
    CANDIDATE_REJECTED = "memory.candidate.rejected"
    RECORD_CREATED = "memory.record.created"
    RECORD_UPDATED = "memory.record.updated"
    RECORD_SUPERSEDED = "memory.record.superseded"
    CONFLICT_DETECTED = "memory.conflict.detected"
    RETRIEVED = "memory.retrieved"
    COMPRESSED = "memory.compressed"


@dataclass(frozen=True)
class MemoryEventRecord:
    """A single emitted memory event."""

    type: str
    memory_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(tz=UTC).isoformat())

    @property
    def family(self) -> str:
        """The event family prefix (always ``memory``)."""
        return self.type.split(".", 1)[0]


MemorySink = Callable[[MemoryEventRecord], None]


class MemoryEventEmitter:
    """Minimal in-process emitter: records events and fans out to subscribers.

    Best-effort: a misbehaving sink never breaks the write/retrieval path.
    """

    def __init__(self) -> None:
        self.events: list[MemoryEventRecord] = []
        self._sinks: list[MemorySink] = []

    def subscribe(self, sink: MemorySink) -> None:
        """Register a sink invoked for every subsequent emit."""
        self._sinks.append(sink)

    def emit(
        self,
        event: MemoryEvent | str,
        *,
        memory_id: str | None = None,
        **metadata: Any,
    ) -> MemoryEventRecord:
        """Record and broadcast an event; returns the recorded event."""
        record = MemoryEventRecord(
            type=str(event), memory_id=memory_id, metadata=dict(metadata)
        )
        self.events.append(record)
        for sink in self._sinks:
            try:
                sink(record)
            except Exception:
                continue
        return record

    def of_type(self, event: MemoryEvent | str) -> list[MemoryEventRecord]:
        """All recorded events of a given type (test/inspection helper)."""
        return [e for e in self.events if e.type == str(event)]
