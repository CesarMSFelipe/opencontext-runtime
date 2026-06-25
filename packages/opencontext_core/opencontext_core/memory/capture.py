"""Memory capture hooks — auto-emit MemoryRecords at SDD phase boundaries.

``MemoryCaptureService`` wraps a ``AgentMemoryStore`` (protocol) and emits
typed events for PHASE_START, PHASE_END, VERIFY_FAILURE, and ARCHIVE_SUMMARY.
Events are deduplicated by ``event_id`` so duplicate calls are silently dropped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from opencontext_core.compat import UTC, StrEnum
from opencontext_core.models.agent_memory import MemoryLayer


class CaptureEventKind(StrEnum):
    """Kinds of memory capture events."""

    PHASE_START = "phase_start"
    PHASE_END = "phase_end"
    VERIFY_FAILURE = "verify_failure"
    ARCHIVE_SUMMARY = "archive_summary"


# Maps CaptureEventKind → target MemoryLayer.
_KIND_TO_LAYER: dict[CaptureEventKind, MemoryLayer] = {
    CaptureEventKind.PHASE_START: MemoryLayer.EPISODIC,
    CaptureEventKind.PHASE_END: MemoryLayer.EPISODIC,
    CaptureEventKind.VERIFY_FAILURE: MemoryLayer.FAILURE,
    CaptureEventKind.ARCHIVE_SUMMARY: MemoryLayer.SEMANTIC,
}


@dataclass
class MemoryCaptureEvent:
    """An event to be captured into memory."""

    kind: CaptureEventKind
    phase: str
    run_id: str
    content: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class MemoryCaptureReceipt:
    """Result of a capture operation."""

    event_id: str
    stored: bool
    record_id: str | None = None
    reason: str | None = None


@runtime_checkable
class AgentMemoryStore(Protocol):
    """Minimal protocol for the memory store used by MemoryCaptureService."""

    def store(self, record: object) -> list[str]:
        """Store a MemoryRecord; return contradicted IDs."""
        ...


class MemoryCaptureService:
    """Captures phase-boundary events as MemoryRecords.

    Deduplicates by ``event_id``: if the same event_id is submitted twice,
    the second call is silently dropped and returns ``stored=False``.
    """

    def __init__(self, store: AgentMemoryStore) -> None:
        self._store = store
        self._seen: set[str] = set()

    def capture(self, event: MemoryCaptureEvent) -> MemoryCaptureReceipt:
        """Emit event to memory. Deduplicates by event_id."""
        if event.event_id in self._seen:
            return MemoryCaptureReceipt(
                event_id=event.event_id,
                stored=False,
                reason="duplicate event_id",
            )

        self._seen.add(event.event_id)
        layer = _KIND_TO_LAYER[event.kind]
        record_id = f"capture:{event.run_id}:{event.phase}:{event.kind.value}"

        try:
            from opencontext_core.models.agent_memory import (
                DecayPolicy,
                MemoryLifecycle,
                MemoryRecord,
            )

            now = datetime.now(tz=UTC)
            record = MemoryRecord(
                id=record_id,
                layer=layer,
                key=f"capture:{event.run_id}:{event.phase}",
                content=event.content,
                decay_policy=DecayPolicy(enabled=False),
                created_at=now,
                updated_at=now,
                run_id=event.run_id,
                provenance="capture",
                lifecycle=MemoryLifecycle.ACTIVE,
            )
            self._store.store(record)
        except Exception as exc:
            return MemoryCaptureReceipt(
                event_id=event.event_id,
                stored=False,
                reason=f"store error: {exc}",
            )

        return MemoryCaptureReceipt(
            event_id=event.event_id,
            stored=True,
            record_id=record_id,
        )
