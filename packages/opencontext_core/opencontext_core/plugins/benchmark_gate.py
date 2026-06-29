"""Benchmark-gate-before-activation (PR-015, SPEC PR-015-BENCH).

A plugin that ships a benchmark suite must pass it before activation when
``benchmark_on_install`` is enabled. The benchmark *framework* (runner, baselines,
metrics) lands in PR-017; PR-015 owns only the activation gate. Absent a runner the
gate is a documented pass-through; a failing suite blocks activation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from opencontext_core.plugins.manifest import PluginManifest

# A benchmark runner takes the manifest and returns True when all declared suites
# pass. Supplied by PR-017; None here means the framework is not present.
BenchmarkRunner = Callable[[PluginManifest], bool]


@dataclass(frozen=True)
class GateResult:
    """Outcome of the benchmark gate."""

    passed: bool
    ran: bool
    reason: str


def benchmark_gate(
    manifest: PluginManifest,
    *,
    enabled: bool,
    runner: BenchmarkRunner | None = None,
) -> GateResult:
    """Gate activation on a plugin's declared benchmark suite.

    - Gate disabled, or the plugin declares no suite -> pass-through (no run).
    - Enabled with suites but no runner (PR-017 framework absent) -> pass-through,
      reason recorded.
    - Enabled with suites and a runner -> block when the suite fails.
    """
    suites = manifest.contributes.benchmark_suites
    if not enabled:
        return GateResult(passed=True, ran=False, reason="gate_disabled")
    if not suites:
        return GateResult(passed=True, ran=False, reason="no_benchmark_suite")
    if runner is None:
        return GateResult(passed=True, ran=False, reason="benchmark_framework_absent")
    try:
        ok = bool(runner(manifest))
    except Exception as exc:  # a crashing runner blocks activation, fail-closed
        return GateResult(passed=False, ran=True, reason=f"benchmark_error: {exc}")
    return GateResult(
        passed=ok, ran=True, reason="benchmark_passed" if ok else "benchmark_failed"
    )
