"""Lightweight hook system for agent lifecycle events.

Allows the AgentOrchestrator to fire callbacks at key lifecycle points
(SESSION_START, PRE_READ, PRE_EDIT, POST_TOOL, STOP) so that the runtime
can react automatically without the user having to run commands manually.
"""

from __future__ import annotations

import enum
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


# DEPRECATED(2.0): dead agent SDK hook system (used only by the deprecated AgentOrchestrator;
# not the live hooks.models.HookEvent). Remove in 2.0.
class HookEvent(enum.Enum):
    """Agent lifecycle events that can be hooked into."""

    SESSION_START = "session_start"
    PRE_READ = "pre_read"
    PRE_EDIT = "pre_edit"
    POST_TOOL = "post_tool"
    STOP = "stop"


@dataclass
class HookContext:
    """Context data passed to hook callbacks."""

    event: HookEvent
    project_root: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


HookCallback = Callable[[HookContext], None]


class HookRegistry:
    """Registry for agent lifecycle hooks.

    Hooks are named callbacks registered per-event. Triggering an event
    calls every registered callback with a HookContext. Individual callback
    failures are caught and logged — they never propagate.
    """

    def __init__(self) -> None:
        self._hooks: dict[HookEvent, list[HookCallback]] = {event: [] for event in HookEvent}

    def register(self, event: HookEvent, callback: HookCallback) -> None:
        """Register a callback for an event.

        Args:
            event: The lifecycle event to hook into.
            callback: Callable that receives a HookContext.
        """
        if callback not in self._hooks[event]:
            self._hooks[event].append(callback)

    def trigger(self, event: HookEvent, **data: Any) -> list[dict[str, Any]]:
        """Trigger all callbacks registered for an event.

        Args:
            event: The event to fire.
            **data: Extra keyword arguments merged into HookContext.data
                    (project_root is popped and set directly on the context).

        Returns:
            List of result dicts, one per callback, each with:
            - ``status``: ``"ok"`` or ``"error"``
            - ``error``: error message (only present on failure)

        Never raises -- individual callback errors are caught and logged.
        """
        context = HookContext(
            event=event,
            project_root=data.pop("project_root", ""),
            data=data,
        )
        results: list[dict[str, Any]] = []
        for callback in self._hooks[event]:
            try:
                callback(context)
                results.append({"status": "ok"})
            except Exception as exc:
                logger.warning("Hook callback failed for %s: %s", event.value, exc)
                results.append({"status": "error", "error": str(exc)})
        return results

    def clear(self) -> None:
        """Remove all registered hooks (useful for testing)."""
        for event in HookEvent:
            self._hooks[event] = []
