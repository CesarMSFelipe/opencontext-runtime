"""Benchmark taxonomy — 13 suites + efficiency benchmark through the schema (SPEC-RI-011-14)."""

from __future__ import annotations

import pytest

from opencontext_core.evaluation.models import (
    CostTriple,
    EfficiencyCaseResult,
    EfficiencyReport,
)
from opencontext_core.models.intelligence import BenchmarkResult, BenchmarkTask
from opencontext_core.runtime_intelligence.benchmarks import (
    BenchmarkSystem,
    efficiency_report_to_results,
)


def _efficiency_report() -> EfficiencyReport:
    return EfficiencyReport(
        cases=[
            EfficiencyCaseResult(
                case_id="case-1",
                con=CostTriple(tokens=1200, tool_calls=1, latency_ms=900.0),
                sin=CostTriple(tokens=9000, tool_calls=12, latency_ms=3000.0),
                con_sufficient=True,
                source_coverage=1.0,
            ),
            EfficiencyCaseResult(
                case_id="case-2",
                con=CostTriple(tokens=2000, tool_calls=1, latency_ms=1100.0),
                sin=CostTriple(tokens=8000, tool_calls=10, latency_ms=2500.0),
                con_sufficient=False,  # parity-insufficient ⇒ not a pass
                source_coverage=0.5,
                reasons=["missing expected source"],
            ),
        ]
    )


def test_thirteen_suites_enumerable() -> None:
    suites = BenchmarkSystem().list_suites()
    assert len(suites) == 13
    assert "first-run" in suites


def test_first_run_resolves_to_tasks_and_results() -> None:
    system = BenchmarkSystem()
    report = _efficiency_report()
    tasks = system.tasks_for("first-run", efficiency_report=report)
    assert tasks and all(isinstance(t, BenchmarkTask) for t in tasks)

    results = system.run_suite("first-run", efficiency_report=report)
    assert all(isinstance(r, BenchmarkResult) for r in results)
    by_id = {r.task_id: r for r in results}
    # Parity verdict is carried honestly: case-2 is a fail, not a fake pass.
    assert by_id["case-1"].success is True
    assert by_id["case-2"].success is False
    assert all(r.measured for r in results)


def test_efficiency_report_converts_through_schema() -> None:
    results = efficiency_report_to_results(_efficiency_report())
    assert len(results) == 2
    assert results[0].tokens == 1200


def test_unimplemented_suite_is_not_measured() -> None:
    results = BenchmarkSystem().run_suite("persona")
    assert len(results) == 1
    assert results[0].measured is False
    assert results[0].success is False
    assert "not measured" in results[0].notes


def test_unknown_suite_raises() -> None:
    with pytest.raises(ValueError):
        BenchmarkSystem().run_suite("does-not-exist")
