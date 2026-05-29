"""Tests for agent lifecycle hook system.

Covers:
- HookRegistry register / trigger / clear
- Multiple handlers per event
- Handler failure isolation (does not propagate)
- HookHandlers default handlers
"""

from __future__ import annotations

from unittest.mock import patch

from opencontext_core.agents.hook_handlers import (
    DEFAULT_HANDLERS,
    on_post_tool,
    on_pre_edit,
    on_pre_read,
    on_session_start,
    on_stop,
)
from opencontext_core.agents.hooks import HookContext, HookEvent, HookRegistry

# ---------------------------------------------------------------------------
# HookRegistry
# ---------------------------------------------------------------------------


class TestHookRegistry:
    def test_register_and_trigger(self) -> None:
        registry = HookRegistry()
        collected: list[str] = []

        def handler(ctx: HookContext) -> None:
            collected.append(ctx.event.value)

        registry.register(HookEvent.SESSION_START, handler)
        registry.trigger(HookEvent.SESSION_START, project_root="/tmp")

        assert collected == ["session_start"]

    def test_register_duplicate_ignored(self) -> None:
        registry = HookRegistry()
        collected: list[str] = []

        def handler(ctx: HookContext) -> None:
            collected.append("hit")

        registry.register(HookEvent.POST_TOOL, handler)
        registry.register(HookEvent.POST_TOOL, handler)  # duplicate
        registry.trigger(HookEvent.POST_TOOL, project_root="/tmp")

        assert collected == ["hit"]  # only called once

    def test_trigger_multiple_handlers(self) -> None:
        registry = HookRegistry()
        results: list[int] = []

        def a(ctx: HookContext) -> None:
            results.append(1)

        def b(ctx: HookContext) -> None:
            results.append(2)

        registry.register(HookEvent.PRE_READ, a)
        registry.register(HookEvent.PRE_READ, b)
        registry.trigger(HookEvent.PRE_READ, project_root="/tmp")

        assert results == [1, 2]

    def test_no_handlers_does_not_raise(self) -> None:
        registry = HookRegistry()
        # No handler registered for STOP
        result = registry.trigger(HookEvent.STOP, project_root="/tmp")
        assert result == []

    def test_handler_failure_isolation(self) -> None:
        registry = HookRegistry()
        results: list[str] = []

        def failing(ctx: HookContext) -> None:
            raise RuntimeError("boom")

        def ok(ctx: HookContext) -> None:
            results.append("ok")

        registry.register(HookEvent.SESSION_START, failing)
        registry.register(HookEvent.SESSION_START, ok)
        trigger_results = registry.trigger(HookEvent.SESSION_START, project_root="/tmp")

        assert results == ["ok"]  # ok handler still ran
        assert len(trigger_results) == 2
        assert trigger_results[0]["status"] == "error"
        assert "boom" in trigger_results[0]["error"]
        assert trigger_results[1]["status"] == "ok"

    def test_trigger_passes_data(self) -> None:
        registry = HookRegistry()
        captured: HookContext | None = None

        def capture(ctx: HookContext) -> None:
            nonlocal captured
            captured = ctx

        registry.register(HookEvent.PRE_EDIT, capture)
        registry.trigger(HookEvent.PRE_EDIT, project_root="/my/proj", file_path="foo.py")

        assert captured is not None
        assert captured.event == HookEvent.PRE_EDIT
        assert captured.project_root == "/my/proj"
        assert captured.data["file_path"] == "foo.py"
        assert captured.timestamp is not None

    def test_clear(self) -> None:
        registry = HookRegistry()
        collected: list[str] = []

        def handler(ctx: HookContext) -> None:
            collected.append("x")

        registry.register(HookEvent.STOP, handler)
        registry.clear()
        registry.trigger(HookEvent.STOP, project_root="/tmp")

        assert collected == []


# ---------------------------------------------------------------------------
# Default hook handlers
# ---------------------------------------------------------------------------


class TestDefaultHandlers:
    def test_on_session_start_logs(self) -> None:
        ctx = HookContext(
            event=HookEvent.SESSION_START,
            project_root="/tmp/proj",
            data={"project": "myapp"},
        )
        with patch("opencontext_core.agents.hook_handlers.logger") as mock_log:
            on_session_start(ctx)
            mock_log.info.assert_called_once()

    def test_on_pre_read_logs(self) -> None:
        ctx = HookContext(
            event=HookEvent.PRE_READ,
            project_root="/tmp",
            data={"file_path": "src/main.py"},
        )
        with patch("opencontext_core.agents.hook_handlers.logger") as mock_log:
            on_pre_read(ctx)
            mock_log.debug.assert_called_once_with("Pre-read: %s", "src/main.py")

    def test_on_pre_edit_logs(self) -> None:
        ctx = HookContext(
            event=HookEvent.PRE_EDIT,
            project_root="/tmp",
            data={"file_path": "src/main.py"},
        )
        with patch("opencontext_core.agents.hook_handlers.logger") as mock_log:
            on_pre_edit(ctx)
            mock_log.debug.assert_called_once_with("Pre-edit: %s", "src/main.py")

    def test_on_post_tool_logs(self) -> None:
        ctx = HookContext(
            event=HookEvent.POST_TOOL,
            project_root="/tmp",
            data={"tool_name": "opencontext_pack", "status": "ok"},
        )
        with patch("opencontext_core.agents.hook_handlers.logger") as mock_log:
            on_post_tool(ctx)
            mock_log.info.assert_called_once_with(
                "Tool executed: %s — status: %s", "opencontext_pack", "ok"
            )

    def test_on_stop_logs(self) -> None:
        ctx = HookContext(
            event=HookEvent.STOP,
            project_root="/tmp",
            data={"reason": "completed"},
        )
        with patch("opencontext_core.agents.hook_handlers.logger") as mock_log:
            on_stop(ctx)
            mock_log.info.assert_called_once_with("Agent stop — reason: %s", "completed")

    def test_default_handlers_structure(self) -> None:
        """All events have at least one default handler."""
        for event in HookEvent:
            assert event in DEFAULT_HANDLERS
            assert len(DEFAULT_HANDLERS[event]) >= 1

    def test_register_defaults(self) -> None:
        """Default handlers can be bulk-registered on a registry."""
        registry = HookRegistry()
        for event, handlers in DEFAULT_HANDLERS.items():
            for handler in handlers:
                registry.register(event, handler)

        results = registry.trigger(HookEvent.SESSION_START, project_root="/tmp")
        assert len(results) == 1
        assert results[0]["status"] == "ok"
