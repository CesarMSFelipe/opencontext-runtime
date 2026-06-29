"""Parity-gate helper: a flag flips to vNext only when parity is proven (CL-012).

A thin harness other PRs (003/010/012) call to assert that a subsystem's legacy
and vNext paths produce equivalent observable output *before* its ``runtime.*``
flag may flip. Until the parity check passes the legacy path stays authoritative;
the registry refuses to route to the vNext adapter (see ``AdapterRegistry.resolve``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict


class ParityGateError(RuntimeError):
    """Raised when a flag is flipped to vNext before its parity check passes."""


class ParityReport(BaseModel):
    """Outcome of comparing a subsystem's legacy and vNext output."""

    model_config = ConfigDict(extra="forbid")

    subsystem: str
    flag: str
    passed: bool
    mismatch: str | None = None


def check_parity(
    subsystem: str,
    flag: str,
    legacy: Any,
    vnext: Any,
    *,
    equals: Callable[[Any, Any], bool] | None = None,
) -> ParityReport:
    """Compare *legacy* vs *vnext* output and return a ``ParityReport``.

    ``equals`` defaults to ``==``; pass a custom comparator for outputs that need
    structural / tolerant equality.
    """
    matched = equals(legacy, vnext) if equals is not None else (legacy == vnext)
    return ParityReport(
        subsystem=subsystem,
        flag=flag,
        passed=bool(matched),
        mismatch=None if matched else f"legacy={legacy!r} != vnext={vnext!r}",
    )


def assert_parity(report: ParityReport) -> None:
    """Raise ``ParityGateError`` if *report* did not pass (gate is red)."""
    if not report.passed:
        raise ParityGateError(
            f"parity gate failed for {report.subsystem} (flag {report.flag}): {report.mismatch}"
        )
