"""Named provider lifecycle events (book §25 "Events"; doc 59 family ``provider``).

The Provider Gateway emits these as it selects, calls, completes, fails, falls
back, or times out on a provider. They belong to the ``provider`` event family
(doc 59 §Event hierarchy) so Studio can render one lane per family. The emitter is
intentionally minimal: it forwards to an optional sink and keeps a local log so
tests and inspection can assert what was emitted without a transport.
"""

from __future__ import annotations

from collections.abc import Callable

from opencontext_core.compat import StrEnum

# Event family (doc 59 §Event hierarchy).
PROVIDER_EVENT_FAMILY = "provider"


class ProviderEvent(StrEnum):
    """The six provider lifecycle events (book §25 "Events")."""

    SELECTED = "provider.selected"
    CALLED = "provider.called"
    COMPLETED = "provider.completed"
    FAILED = "provider.failed"
    FALLBACK = "provider.fallback"
    TIMEOUT = "provider.timeout"


# A sink receives ``(event, payload)``.
ProviderEventSink = Callable[[ProviderEvent, dict[str, object]], None]


class ProviderEventEmitter:
    """Minimal in-process emitter: forwards to a sink and keeps a local log."""

    def __init__(self, sink: ProviderEventSink | None = None) -> None:
        self._sink = sink
        self.events: list[tuple[ProviderEvent, dict[str, object]]] = []

    def emit(self, event: ProviderEvent, **payload: object) -> None:
        """Record an event locally and forward it to the sink, if any."""

        self.events.append((event, payload))
        if self._sink is not None:
            self._sink(event, payload)

    def kinds(self) -> list[ProviderEvent]:
        """Return the ordered event kinds emitted so far (inspection helper)."""

        return [event for event, _ in self.events]
