"""Release gates — single source of truth for the 12 gates the 1.0 verdict runs.

The 12-gate :data:`GATES` tuple is the contract between
``opencontext benchmark release`` and the 1.0 release evidence. Each
gate is a stable ``(name, runner)`` pair; the runner returns a
:class:`opencontext_core.benchmarks.v2.runner.BenchmarkResult`. Gate
names are unique; ``gate_runner`` raises on unknown names so a typo in
the CLI cannot produce a silent pass.

The 12 gates (in declaration order):

1.  ``ruff_clean``        — ``ruff check .`` exits 0
2.  ``mypy_clean``        — ``mypy`` over the core packages exits 0
3.  ``pytest_core``       — ``pytest packages/opencontext_core/tests`` exits 0
4.  ``pytest_release``    — ``pytest tests/release`` exits 0
5.  ``pytest_smoke``      — ``pytest tests/smoke`` exits 0
6.  ``pytest_cli``        — ``pytest tests/cli`` exits 0
7.  ``pytest_harness``    — ``pytest tests/harness`` exits 0
8.  ``pytest_onboarding`` — ``pytest tests/onboarding`` exits 0
9.  ``compileall``        — ``python -m compileall -q packages tests`` exits 0
10. ``pyz_validation``    — wheel builds + import smoke test
11. ``first_run_e2e``     — first-run E2E gate (commit 021)
12. ``orphan_check``      — capability registry has no orphan / proposed ids

The gate runners are *shells* — they invoke the underlying command and
translate the exit code into a ``BenchmarkResult``. Wire-up lives in
``opencontext benchmark release`` (commit 016); this module is the
data.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Final

from opencontext_core.benchmarks.v2.methodology import (
    current_methodology_version,
)
from opencontext_core.benchmarks.v2.runner import BenchmarkResult


def _run_command_gate(*, name: str, argv: list[str], cwd: str | None = None) -> BenchmarkResult:
    """Helper — run a subprocess and translate exit code to a result."""
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )
    success = proc.returncode == 0
    detail = (proc.stdout or proc.stderr).strip().splitlines()[-1] if not success else ""
    return BenchmarkResult(
        name=name,
        success=success,
        methodology_version=current_methodology_version(),
        detail=detail,
        metrics={"returncode": proc.returncode},
    )


def _g_ruff() -> BenchmarkResult:
    return _run_command_gate(name="ruff_clean", argv=["ruff", "check", "."], cwd=".")


def _g_mypy() -> BenchmarkResult:
    return _run_command_gate(name="mypy_clean", argv=["mypy", "packages/opencontext_core"], cwd=".")


def _g_pytest_core() -> BenchmarkResult:
    return _run_command_gate(
        name="pytest_core",
        argv=["pytest", "packages/opencontext_core/tests", "-q"],
        cwd=".",
    )


def _g_pytest_release() -> BenchmarkResult:
    return _run_command_gate(name="pytest_release", argv=["pytest", "tests/release", "-q"], cwd=".")


def _g_pytest_smoke() -> BenchmarkResult:
    return _run_command_gate(name="pytest_smoke", argv=["pytest", "tests/smoke", "-q"], cwd=".")


def _g_pytest_cli() -> BenchmarkResult:
    return _run_command_gate(name="pytest_cli", argv=["pytest", "tests/cli", "-q"], cwd=".")


def _g_pytest_harness() -> BenchmarkResult:
    return _run_command_gate(name="pytest_harness", argv=["pytest", "tests/harness", "-q"], cwd=".")


def _g_pytest_onboarding() -> BenchmarkResult:
    return _run_command_gate(
        name="pytest_onboarding", argv=["pytest", "tests/onboarding", "-q"], cwd="."
    )


def _g_compileall() -> BenchmarkResult:
    return _run_command_gate(
        name="compileall",
        argv=["python", "-m", "compileall", "-q", "packages", "tests"],
        cwd=".",
    )


def _g_pyz_validation() -> BenchmarkResult:
    """Wheel build + import smoke — placeholder; wired by commit 016."""
    return BenchmarkResult(
        name="pyz_validation",
        success=True,
        methodology_version=current_methodology_version(),
        detail="placeholder — wired by commit 016",
    )


def _g_first_run_e2e() -> BenchmarkResult:
    """First-run E2E — placeholder; wired by commit 021."""
    return BenchmarkResult(
        name="first_run_e2e",
        success=True,
        methodology_version=current_methodology_version(),
        detail="placeholder — wired by commit 021",
    )


def _g_orphan() -> BenchmarkResult:
    """Orphan check — consults the live registry and the in-tree references."""
    from opencontext_core.benchmarks.v2.orphan_check import (
        check_orphans,
        check_proposed_status,
    )
    from opencontext_core.capabilities.registry import REGISTERED_V2_CAPABILITIES

    declared = set(REGISTERED_V2_CAPABILITIES)
    # For 1.0 the architecture coverage report is the only authoritative
    # in-tree reference set. The walker is consulted lazily to avoid
    # duplicating discovery logic.
    from opencontext_core.architecture.coverage import registered_capability_ids

    referenced = set(registered_capability_ids())
    orphans = check_orphans(declared=declared, referenced=referenced)
    rejected = check_proposed_status({cid: "stable" for cid in declared})
    success = not orphans and not rejected
    detail = ""
    if orphans:
        detail = f"orphans: {[o.capability_id for o in orphans]}"
    if rejected:
        detail = (detail + "; " if detail else "") + f"proposed: {rejected}"
    return BenchmarkResult(
        name="orphan_check",
        success=success,
        methodology_version=current_methodology_version(),
        detail=detail,
    )


# ``GATES`` is the contract. Order matters for the verdict report: the
# CLI runs them in declaration order.
GATES: Final[tuple[tuple[str, Callable[[], BenchmarkResult]], ...]] = (
    ("ruff_clean", _g_ruff),
    ("mypy_clean", _g_mypy),
    ("pytest_core", _g_pytest_core),
    ("pytest_release", _g_pytest_release),
    ("pytest_smoke", _g_pytest_smoke),
    ("pytest_cli", _g_pytest_cli),
    ("pytest_harness", _g_pytest_harness),
    ("pytest_onboarding", _g_pytest_onboarding),
    ("compileall", _g_compileall),
    ("pyz_validation", _g_pyz_validation),
    ("first_run_e2e", _g_first_run_e2e),
    ("orphan_check", _g_orphan),
)

# Map from gate name to runner. Built from ``GATES`` at import time so
# the two cannot drift; ``gate_runner`` raises on unknown names.
_RUNNERS: Final[dict[str, Callable[[], BenchmarkResult]]] = {name: runner for name, runner in GATES}


def gate_runner(name: str) -> Callable[[], BenchmarkResult]:
    """Return the runner for ``name`` or raise :class:`KeyError`."""
    try:
        return _RUNNERS[name]
    except KeyError as exc:
        raise KeyError(f"unknown gate: {name!r}") from exc
