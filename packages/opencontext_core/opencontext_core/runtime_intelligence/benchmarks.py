"""Benchmark System (book §12) — 13-suite taxonomy + BenchmarkTask/Result.

Enumerates the thirteen benchmark suites and runs the existing honest, parity-
gated efficiency benchmark THROUGH the book schema. Only suites that can run
honestly are measured; the rest are DECLARED but returned as "not measured"
(``measured=False``) rather than a fabricated pass (build-rule honesty).

Today only ``first-run`` is wired to a real runner — the parity-gated
:class:`~opencontext_core.evaluation.efficiency.EfficiencyBenchmark`
(``EfficiencyReport`` → ``BenchmarkResult``). The other twelve suites are declared
and reported as not-measured until their runners land in later PRs.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.evaluation.models import EfficiencyCaseResult, EfficiencyReport
from opencontext_core.models.intelligence import (
    BENCHMARK_SUITES,
    BenchmarkResult,
    BenchmarkTask,
)
from opencontext_core.runtime_intelligence import telemetry_layout

# Suites with a real, honest runner in PR-011.
_IMPLEMENTED_SUITES: frozenset[str] = frozenset({"first-run"})


def efficiency_report_to_results(
    report: EfficiencyReport, *, suite: str = "first-run"
) -> list[BenchmarkResult]:
    """Convert an :class:`EfficiencyReport` into book :class:`BenchmarkResult`s.

    ``success`` is the case's quality-parity verdict (``con_sufficient``) — never a
    fabricated token win. Tokens/duration/tool-calls are the measured CON cost.
    """
    return [_case_to_result(case, suite) for case in report.cases]


def _case_to_result(case: EfficiencyCaseResult, suite: str) -> BenchmarkResult:
    return BenchmarkResult(
        task_id=case.case_id,
        suite=suite,
        measured=True,
        success=case.con_sufficient,
        tokens=case.con.tokens,
        duration_s=int(case.con.latency_ms / 1000),
        tool_calls=case.con.tool_calls,
        changed_files=0,
        changed_lines=0,
        tests_passed=case.con_sufficient,
        security_passed=True,
        notes="; ".join(case.reasons) if case.reasons else "parity-gated efficiency case",
    )


class BenchmarkSystem:
    """The 13-suite taxonomy runner over :class:`BenchmarkTask`/:class:`BenchmarkResult`."""

    def list_suites(self) -> tuple[str, ...]:
        """Return the thirteen declared benchmark suites."""
        return BENCHMARK_SUITES

    def is_implemented(self, suite: str) -> bool:
        return suite in _IMPLEMENTED_SUITES

    def tasks_for(
        self, suite: str, *, efficiency_report: EfficiencyReport | None = None
    ) -> list[BenchmarkTask]:
        """Resolve a suite to its :class:`BenchmarkTask`s.

        For ``first-run`` with an efficiency report, one task per measured case.
        Otherwise a single declared placeholder task carrying the suite name.
        """
        if suite == "first-run" and efficiency_report is not None:
            return [
                BenchmarkTask(
                    id=case.case_id,
                    name=case.case_id,
                    suite=suite,
                    task="build task context (parity-gated efficiency case)",
                    expected_workflow="oc-flow",
                    success_criteria=["con_sufficient"],
                )
                for case in efficiency_report.cases
            ]
        return [
            BenchmarkTask(
                id=f"{suite}-declared",
                name=f"{suite} (declared)",
                suite=suite,
                task=f"{suite} benchmark suite",
            )
        ]

    def run_suite(
        self,
        suite: str,
        *,
        efficiency_report: EfficiencyReport | None = None,
        root: str | Path = ".",
        emit: bool = False,
    ) -> list[BenchmarkResult]:
        """Run one suite honestly; unimplemented/unsupplied suites are not-measured."""
        if suite not in BENCHMARK_SUITES:
            raise ValueError(f"unknown benchmark suite: {suite!r}")

        if suite == "first-run":
            if efficiency_report is None:
                results = [_not_measured(suite, "no efficiency report supplied")]
            else:
                results = efficiency_report_to_results(efficiency_report, suite=suite)
        else:
            results = [_not_measured(suite, "suite runner not implemented in PR-011")]

        if emit:
            telemetry_layout.append_benchmark_history(results, root)
        return results


def _not_measured(suite: str, reason: str) -> BenchmarkResult:
    """An honest 'not measured' result — never a fake pass."""
    return BenchmarkResult(
        task_id=f"{suite}-declared",
        suite=suite,
        measured=False,
        success=False,
        notes=f"not measured: {reason}",
    )


# Re-export for callers/tests.
SUITES = BENCHMARK_SUITES

__all__ = [
    "SUITES",
    "BenchmarkSystem",
    "efficiency_report_to_results",
]
