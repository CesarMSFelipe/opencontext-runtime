"""Default hook handlers for agent lifecycle events.

Each handler is a function matching the HookCallback signature
(HookContext) -> None. They are registered with HookRegistry to
run automatically at the corresponding agent lifecycle event.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .hooks import HookContext, HookEvent

logger = logging.getLogger(__name__)


def on_session_start(context: HookContext) -> None:
    """Log session start with project and event info."""
    project = context.data.get("project", Path(context.project_root).name)
    logger.info(
        "Agent session started — project: %s, root: %s",
        project,
        context.project_root,
    )


def on_pre_read(context: HookContext) -> None:
    """Log when the agent is about to read a file."""
    file_path = context.data.get("file_path", "<unknown>")
    logger.debug("Pre-read: %s", file_path)


def on_pre_edit(context: HookContext) -> None:
    """Log when the agent is about to edit a file."""
    file_path = context.data.get("file_path", "<unknown>")
    logger.debug("Pre-edit: %s", file_path)


def on_post_tool(context: HookContext) -> None:
    """Log after a tool execution completes."""
    tool_name = context.data.get("tool_name", "<unknown>")
    status = context.data.get("status", "unknown")
    logger.info("Tool executed: %s — status: %s", tool_name, status)


def on_stop(context: HookContext) -> None:
    """Log agent stop with optional reason."""
    reason = context.data.get("reason", "completed")
    logger.info("Agent stop — reason: %s", reason)


# Map events to their default handlers for bulk registration.
DEFAULT_HANDLERS: dict[HookEvent, list[callable]] = {
    HookEvent.SESSION_START: [on_session_start],
    HookEvent.PRE_READ: [on_pre_read],
    HookEvent.PRE_EDIT: [on_pre_edit],
    HookEvent.POST_TOOL: [on_post_tool],
    HookEvent.STOP: [on_stop],
}
