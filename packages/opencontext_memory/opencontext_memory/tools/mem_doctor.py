"""mem_doctor — thin wrapper over :func:`opencontext_memory.diagnostic.collect_findings`.

REQ-OMT-018 / REQ-OMT-021 — ``mem_doctor(store) -> DoctorReport``.

PR2.c.ii shipped a 3-check surface (size, conflicts, retention). PR2.d
adds the 4th check (``lifecycle``) by extracting the aggregator into
:mod:`opencontext_memory.diagnostic`. This wrapper delegates so the
public tool name (``mem_doctor``) stays stable for CLI/FastAPI callers
and PR2.c.ii test assertions (``"size" in report.checks``, etc.)
keep passing without modification.
"""

from __future__ import annotations

from typing import Any

from opencontext_memory.diagnostic import DoctorReport, collect_findings


def mem_doctor(store: Any) -> DoctorReport:
    """Aggregate findings from all 4 memory-health checks.

    Returns a :class:`opencontext_memory.diagnostic.DoctorReport`. Identical
    to calling :func:`opencontext_memory.diagnostic.collect_findings`
    directly — this wrapper exists only so the tool surface name stays
    stable across PR2.c and PR2.d.
    """
    return collect_findings(store)


__all__ = ["DoctorReport", "mem_doctor"]
