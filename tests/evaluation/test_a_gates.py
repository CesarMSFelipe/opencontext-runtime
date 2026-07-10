"""VDM-008: the provider-free A-gates MEASURE; the two provider-CI gates stay deferred.

* ``sdd-formal-feature`` + ``plugin-compatibility`` MEASURE off golden fixtures.
* ``memory-usefulness`` MEASURES off a deterministic seeded backend.
* ``kg-retrieval-precision`` + ``context-token-efficiency`` ship hooks but stay
  NOT_MEASURED (Option A) — never FAILED, never a fake MET — and their NOT_MEASURED
  status does NOT force ``ready=False``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.evaluation.golden import GOLDEN_ROOT, GoldenSuite, clear_golden_cache
from opencontext_core.evaluation.models import GateStatus
from opencontext_core.evaluation.runner import RunnerConfig, build_default_runner
from opencontext_core.memory.benchmark import run_seeded_memory_benchmark, seeded_memory_provider
from opencontext_core.operating_model.release_gate import (
    DEFERRED_PROVIDER_CI_GATES,
    FUNCTIONAL_BEHAVIOURS,
    GOVERNANCE_GATES,
    AcceptanceEvaluator,
    GateResult,
    ReleaseGateRunner,
    ReleaseMetrics,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_sdd_formal_feature_measures_provider_free() -> None:
    clear_golden_cache()
    report = GoldenSuite("sdd-formal-feature", GOLDEN_ROOT).run(Path("."))
    assert report.status in {GateStatus.MET, GateStatus.FAILED}
    assert report.status is not GateStatus.NOT_MEASURED
    assert report.status is GateStatus.MET, report.notes


def test_plugin_compatibility_measures_provider_free() -> None:
    clear_golden_cache()
    report = GoldenSuite("plugin-compatibility", GOLDEN_ROOT).run(Path("."))
    assert report.status in {GateStatus.MET, GateStatus.FAILED}
    assert report.status is GateStatus.MET, report.notes


def test_memory_usefulness_measures_against_seeded_backend() -> None:
    result = run_seeded_memory_benchmark()
    assert result.num_questions > 0
    assert result.recall_at_5 >= 0.85 and result.mrr >= 0.70
    runner = build_default_runner(RunnerConfig(memory_provider=seeded_memory_provider()))
    report = runner.run("memory-usefulness", ".")
    assert report.status is GateStatus.MET, report.notes


def test_provider_ci_gates_not_measured_never_failed() -> None:
    runner = build_default_runner()  # no recall/efficiency provider hooks
    for name in DEFERRED_PROVIDER_CI_GATES:
        report = runner.run(name, ".")
        assert report.status is GateStatus.NOT_MEASURED
        assert report.status is not GateStatus.FAILED


@pytest.mark.slow
def test_deferred_gates_do_not_block_ready() -> None:
    """With every other gate MET and only the two deferred gates NOT_MEASURED, the
    verdict is ready=True (Option A) — and the deferred gates are annotated as such."""
    functional = {name: GateStatus.MET for name in FUNCTIONAL_BEHAVIOURS}
    governance = {name: GateStatus.MET for name in GOVERNANCE_GATES}
    regression = {
        name: GateStatus.MET
        for name in (
            "suite-green",
            "gate-k-12-12",
            "mypy-strict-clean",
            "ruff-clean",
            "forbidden-names-clean",
        )
    }
    dod = [
        GateResult(gate=n, category="C", status=GateStatus.MET, detail="ok")
        for n in (
            "no-first-run-regression",
            "no-benchmark-quality-regression",
            "no-uncontrolled-token-increase",
            "no-critical-policy-bypass",
        )
    ]
    verdict = AcceptanceEvaluator(repo_root=PROJECT_ROOT).evaluate(
        bench_root=str(PROJECT_ROOT),
        functional=functional,
        governance=governance,
        regression=regression,
        dod_gates=dod,
        e2e_proof={"passed": True, "steps": [{"step": "all", "ok": True}]},
    )
    assert verdict.ready is True
    assert verdict.failed == 0
    not_measured = {g.gate for g in verdict.gates if g.status is GateStatus.NOT_MEASURED}
    assert not_measured == set(DEFERRED_PROVIDER_CI_GATES)
    for g in verdict.gates:
        if g.gate in DEFERRED_PROVIDER_CI_GATES:
            assert "DEFERRED" in g.detail and "DEFERRED_PROVIDER_CI.md" in g.detail


def test_release_metrics_dod_baseline_helper_is_importable() -> None:
    # The DoD baseline gates wire through ReleaseGateRunner (kept stable for VDM-006).
    gates = ReleaseGateRunner().evaluate(ReleaseMetrics(), None)
    assert all(g.status is GateStatus.MET for g in gates)
