"""REQ-bench-v1-001/002: BenchmarkRunner + methodology versioning."""

from __future__ import annotations

from opencontext_core.benchmarks.v2.methodology import (
    current_methodology_version,
    validate_methodology_version,
)
from opencontext_core.benchmarks.v2.runner import (
    BenchmarkResult,
    BenchmarkRunner,
    BenchmarkTask,
)


def test_runner_runs_all_tasks() -> None:
    runner = BenchmarkRunner()
    runner.register(
        BenchmarkTask(
            name="t1",
            run=lambda: BenchmarkResult(
                name="t1", success=True, methodology_version=current_methodology_version()
            ),
        )
    )
    runner.register(
        BenchmarkTask(
            name="t2",
            run=lambda: BenchmarkResult(
                name="t2", success=True, methodology_version=current_methodology_version()
            ),
        )
    )
    results = runner.run_all()
    assert [r.name for r in results] == ["t1", "t2"]
    assert all(r.success for r in results)


def test_runner_returns_results_in_order() -> None:
    runner = BenchmarkRunner()
    for n in ("a", "b", "c"):
        runner.register(
            BenchmarkTask(
                name=n,
                run=lambda n=n: BenchmarkResult(
                    name=n, success=True, methodology_version=current_methodology_version()
                ),
            )
        )
    assert [r.name for r in runner.run_all()] == ["a", "b", "c"]


def test_methodology_version_schema_style() -> None:
    v = current_methodology_version()
    parts = v.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_validate_methodology_version_ok() -> None:
    validate_methodology_version(current_methodology_version())
