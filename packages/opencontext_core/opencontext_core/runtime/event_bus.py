"""Event bus with an append-only JSONL default (SPEC RC-005).

``EventBus`` provides ``publish`` + ``subscribe`` with synchronous fan-out.
``JsonlEventBus`` additionally appends each event as one JSON line to a session
``events.jsonl`` and never rewrites or truncates prior lines.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from opencontext_core.runtime.events import RuntimeEvent


@runtime_checkable
class EventConsumer(Protocol):
    """A subscriber that receives published events in publish order."""

    def on_event(self, event: RuntimeEvent) -> None: ...


class EventBus:
    """Base event bus: persist (hook) then fan out to subscribers.

    The base ``_persist`` is a no-op; subclasses override it for durable
    transports. Subscribers are always notified in registration order.
    """

    def __init__(self) -> None:
        self._subscribers: list[EventConsumer] = []

    def subscribe(self, consumer: EventConsumer) -> None:
        self._subscribers.append(consumer)

    def publish(self, event: RuntimeEvent) -> RuntimeEvent:
        self._persist(event)
        for consumer in self._subscribers:
            consumer.on_event(event)
        return event

    def _persist(self, event: RuntimeEvent) -> None:
        """Durable-transport hook; the base bus persists nothing."""


class JsonlEventBus(EventBus):
    """Append-only JSONL event bus bound to one session ``events.jsonl``."""

    def __init__(self, events_path: Path | str) -> None:
        super().__init__()
        self.events_path = Path(events_path)

    def _persist(self, event: RuntimeEvent) -> None:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        # Open in append mode so prior lines are never rewritten or truncated.
        with open(self.events_path, "a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")


class CollectingConsumer:
    """In-memory test collector: records events in publish order."""

    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []

    def on_event(self, event: RuntimeEvent) -> None:
        self.events.append(event)

    @property
    def types(self) -> list[str]:
        return [event.type for event in self.events]
