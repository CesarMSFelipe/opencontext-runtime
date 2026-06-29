"""Runtime Simulator — provider-free dry run + scheduler wiring (SPEC-RI-011-12)."""

from __future__ import annotations

from opencontext_core.models.intelligence import SimulationReport
from opencontext_core.runtime_intelligence.simulator import (
    RuntimeSimulator,
    SchedulerPlanEstimator,
)


class _ProviderSpy:
    """Any access means a provider call was attempted (must never happen)."""

    def __getattr__(self, name: str) -> object:  # pragma: no cover - guard
        raise AssertionError(f"simulator made a provider call: {name}")


def test_simulate_makes_no_provider_call(tmp_path) -> None:
    # The simulator takes no provider; the report asserts provider_calls == 0.
    sim = RuntimeSimulator()
    report = sim.simulate("fix the parser bug", root=tmp_path)
    assert isinstance(report, SimulationReport)
    assert report.provider_calls == 0
    assert report.recommended_workflow in {"oc-flow", "sdd"}
    assert report.recommended_lane in {"quick", "fast", "full"}
    assert report.cost_estimates  # at least one estimate


def test_simulate_uses_local_kg_search_only() -> None:
    calls: list[str] = []

    def kg_search(task: str) -> tuple[list[str], list[str]]:
        calls.append(task)
        return (["parser.py"], ["parse"])

    sim = RuntimeSimulator(kg_search=kg_search)
    report = sim.simulate("fix the parser bug")
    assert report.expected_files == ["parser.py"]
    assert report.expected_symbols == ["parse"]
    assert calls  # the local KG callable was used, no provider


def test_security_task_flags_risk_and_recommends_sdd() -> None:
    sim = RuntimeSimulator()
    report = sim.simulate("patch the SQL injection vulnerability")
    assert "security_sensitive" in report.risk_flags
    assert report.recommended_workflow == "sdd"


def test_scheduler_simulate_wired_to_real_estimator() -> None:
    from opencontext_core.runtime.brain import RuntimeBrain
    from opencontext_core.runtime.scheduler import RuntimeScheduler

    scheduler = RuntimeScheduler(RuntimeBrain(), estimator=SchedulerPlanEstimator())
    report = scheduler.simulate({"run_id": "run_x", "task": "add a feature", "nodes": ["a", "b"]})
    assert report.estimator == "runtime_intelligence"
    assert report.estimated_tokens and report.estimated_tokens > 0
    assert report.estimated_duration_ms and report.estimated_duration_ms > 0


def test_scheduler_simulate_without_estimator_is_stub() -> None:
    from opencontext_core.runtime.brain import RuntimeBrain
    from opencontext_core.runtime.scheduler import RuntimeScheduler

    scheduler = RuntimeScheduler(RuntimeBrain())
    report = scheduler.simulate({"run_id": "run_y", "nodes": ["a"]})
    assert report.estimator == "stub"
