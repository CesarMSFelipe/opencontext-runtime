"""Trace-id propagation context for the opencontext_sdd orchestrator."""

from __future__ import annotations

import secrets
import threading
from collections.abc import Iterator
from contextlib import contextmanager

_local = threading.local()


def emit_trace_id() -> str:
    """Return a fresh 16-character hex trace identifier."""
    return secrets.token_hex(8)


def current_trace_id() -> str | None:
    """Return the trace_id active on this thread, or ``None`` if none is set."""
    return getattr(_local, "trace_id", None)


@contextmanager
def with_trace_id(trace_id: str | None = None) -> Iterator[str]:
    """Set ``trace_id`` as the active id for this thread for the duration of the block.

    If ``trace_id`` is ``None``, a fresh id is generated via :func:`emit_trace_id`.
    On exit, the previous trace_id (if any) is restored, so nested contexts work.
    Yields the active trace_id so callers can capture it without
    :func:`current_trace_id`.
    """
    tid = trace_id or emit_trace_id()
    previous = current_trace_id()
    _local.trace_id = tid
    try:
        yield tid
    finally:
        _local.trace_id = previous
