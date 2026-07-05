"""Prompt execution must survive an already-running asyncio event loop.

TUI suspend paths (the config menu's guided setup, plugin manager, etc.)
invoke ``opencontext_core.prompts`` while the Textual app's asyncio loop is
still current on the main thread. prompt_toolkit refuses to start a nested
loop there, so without special handling the arrow-key selectors silently
degrade to the plain-text fallback and leak an un-awaited coroutine warning.

``prompts._execute`` must detect the running loop and run the prompt on a
worker thread (fresh loop) instead, keeping one arrow-key UX everywhere.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from opencontext_core import prompts


class _RecordingPrompt:
    """Stand-in for an InquirerPy prompt that records its execution context."""

    def __init__(self, record: dict[str, Any]) -> None:
        self._record = record

    def execute(self) -> str:
        try:
            asyncio.get_running_loop()
            self._record["saw_running_loop"] = True
        except RuntimeError:
            self._record["saw_running_loop"] = False
        self._record["thread"] = threading.current_thread().name
        return "chosen"


def test_execute_inline_without_running_loop() -> None:
    record: dict[str, Any] = {}
    result = prompts._execute(_RecordingPrompt(record))
    assert result == "chosen"
    assert record["saw_running_loop"] is False
    assert record["thread"] == threading.current_thread().name


def test_execute_moves_to_worker_thread_when_loop_is_running() -> None:
    record: dict[str, Any] = {}

    async def scenario() -> str:
        # Synchronous call while this thread's loop is running — exactly what
        # a Textual ``app.suspend()`` handler does.
        return prompts._execute(_RecordingPrompt(record))

    result = asyncio.run(scenario())
    assert result == "chosen"
    # The prompt must NOT see the outer running loop (fresh-thread execution),
    # otherwise prompt_toolkit raises and the UX degrades to text fallback.
    assert record["saw_running_loop"] is False
    assert record["thread"] != threading.current_thread().name


def test_execute_propagates_prompt_errors() -> None:
    class _Boom:
        def execute(self) -> None:
            raise KeyboardInterrupt

    async def scenario() -> None:
        prompts._execute(_Boom())

    try:
        asyncio.run(scenario())
    except KeyboardInterrupt:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("KeyboardInterrupt should propagate")
