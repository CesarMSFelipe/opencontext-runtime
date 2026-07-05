"""opencontext_memory.tools — MCP-style tool surface.

PR2.b ships the dispatcher skeleton + :func:`mem_save`. PR2.c ports the
remaining 18 tools (eager + deferred + admin). Every tool routes through
:func:`opencontext_memory.tools.registry.dispatch` so a CLI verb or FastAPI
endpoint can invoke it by name without importing the concrete module.

The :class:`MemoryTools` protocol on the package root is what the
``MemoryProvider`` Protocol (PR2.d) will hook into — for now the dispatcher
is a thin name→callable map.
"""

from __future__ import annotations

from opencontext_memory.tools.registry import MemoryTools, dispatch, register_tool

__all__ = ["MemoryTools", "dispatch", "register_tool"]
