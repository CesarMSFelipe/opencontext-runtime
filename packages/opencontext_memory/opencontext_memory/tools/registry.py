"""tools.registry — name→callable dispatcher for memory tools.

PR2.b ships the skeleton + ``mem_save`` registration. PR2.c fills out the
rest. The dispatcher is intentionally a flat dict so a CLI verb or FastAPI
endpoint can invoke any tool with ``dispatch(name, **kwargs)`` and never
needs to know which module owns it.

Usage::

    from opencontext_memory.tools import registry
    from opencontext_memory.tools import mem_save as mem_save_mod

    registry.register_tool("mem_save", mem_save_mod.mem_save)
    receipt = registry.dispatch("mem_save", project="P", content="...", ...)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class MemoryTools(Protocol):
    """Protocol every registered tool satisfies.

    Tools are bare callables that accept keyword arguments and return a
    JSON-serialisable value (``SaveReceipt``, ``dict``, ``list[dict]``, ...).
    The protocol shape documents the contract without forcing tools to share
    a base class.
    """

    def __call__(self, **kwargs: Any) -> Any: ...


# Module-level registry. Populated by ``register_tool`` on import; consumers
# only ever go through ``dispatch``.
_REGISTRY: dict[str, Callable[..., Any]] = {}


class UnknownToolError(KeyError):
    """Raised when ``dispatch`` cannot resolve ``name``.

    Inherits from ``KeyError`` so callers that already catch ``KeyError``
    keep working; the explicit subclass lets the CLI surface a friendly
    ``unknown_tool:<name>`` message instead of a stack trace.
    """


def register_tool(name: str, fn: Callable[..., Any]) -> None:
    """Register (or replace) one tool under ``name``.

    Re-registration with the same name is allowed (used by tests to swap in
    fakes); cross-process there is exactly one writer per process so this
    is not a contention concern.
    """
    _REGISTRY[str(name)] = fn


def dispatch(name: str, **kwargs: Any) -> Any:
    """Invoke the tool registered under ``name`` with ``kwargs``.

    ``UnknownToolError`` (``unknown_tool:<name>``) bubbles up to the CLI /
    FastAPI layer verbatim so the surface can format it as a 4xx response.
    """
    try:
        fn = _REGISTRY[name]
    except KeyError as exc:
        raise UnknownToolError(f"unknown_tool:{name}") from exc
    return fn(**kwargs)


def known_tools() -> list[str]:
    """Sorted list of registered tool names (read-only debug helper)."""
    return sorted(_REGISTRY)


__all__ = ["MemoryTools", "UnknownToolError", "dispatch", "known_tools", "register_tool"]
