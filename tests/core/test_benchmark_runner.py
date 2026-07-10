"""BenchmarkRunner + named cognitive suites + versioning (REL-08/REL-09/REL-CONV)."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.evaluation.models import (
    CostTriple,
    EfficiencyCaseResult,
    EfficiencyReport,
    GateStatus,
)
from opencontext_core.evaluation.runner import (
    MANDATORY_GATES,
    BenchmarkRunner,
    EfficiencySuite,
    MemorySuite,
    RecallSuite,
    RunnerConfig,
    build_default_runner,
)


def _case(sufficient: bool) -> EfficiencyCaseResult:
    return EfficiencyCaseResult(
        case_id="c1",
        con=CostTriple(tokens=100, tool_calls=1, latency_ms=5.0),
        sin=CostTriple(tokens=400, tool_calls=6, latency_ms=20.0),
        con_sufficient=sufficient,
        source_coverage=1.0 if sufficient else 0.4,
    )


def test_registry_lists_the_ten_mandatory_gates() -> None:
    runner = build_default_runner()
    assert runner.list_suites() == list(MANDATORY_GATES)
    assert len(MANDATORY_GATES) == 10


# The eight gates that MEASURE off real fixtures / seeded backend without a live
# provider (B4/B5/AVH-006/VDM-008): seven golden suites + the seeded memory gate.
_MEASURED_GATES = {
    "first-run",
    "oc-flow-localized-bugfix",
    "policy-security",
    "resume-rollback",
    "provider-fallback",
    "sdd-formal-feature",
    "plugin-compatibility",
    "memory-usefulness",
}
# The two provider-CI gates stay NOT_MEASURED without a provider hook (Option A).
_PROVIDER_CI_GATES = {"context-token-efficiency", "kg-retrieval-precision"}


@pytest.mark.slow
def test_default_runner_measures_golden_gates_and_versions_all() -> None:
    reports = build_default_runner().run_all(".")
    assert len(reports) == 10
    for r in reports:
        assert r.suite and r.version  # REL-09: every report stamped suite + semver
    measured = {r.suite for r in reports if r.status is not GateStatus.NOT_MEASURED}
    # The eight provider-free gates MEASURE (MET/FAILED), never NOT_MEASURED.
    assert _MEASURED_GATES <= measured
    for r in reports:
        if r.suite in _MEASURED_GATES:
            assert r.status in {GateStatus.MET, GateStatus.FAILED}
            assert r.measured is True
        else:
            # The two provider-CI gates stay honestly NOT_MEASURED — never a fake pass.
            assert r.suite in _PROVIDER_CI_GATES
            assert r.status is GateStatus.NOT_MEASURED
            assert r.measured is False and r.success is False
            assert r.notes.startswith("not measured")


def test_efficiency_suite_met_when_parity_holds(tmp_path: Path) -> None:
    suite = EfficiencySuite(provider=lambda root, smoke: EfficiencyReport(cases=[_case(True)]))
    report = suite.run(tmp_path)
    assert report.status is GateStatus.MET
    assert report.success is True and report.measured is True
    assert report.tokens == 100 and report.tool_calls == 1


def test_efficiency_suite_failed_when_parity_breaks(tmp_path: Path) -> None:
    suite = EfficiencySuite(provider=lambda root, smoke: EfficiencyReport(cases=[_case(False)]))
    report = suite.run(tmp_path)
    assert report.status is GateStatus.FAILED
    assert report.success is False and report.measured is True


def test_recall_and_memory_suites_wire_real_thresholds(tmp_path: Path) -> None:
    class _Recall:
        results = (object(),)
        median_recall = 0.9
        median_precision = 0.6

    class _Mem:
        recall_at_5 = 0.9
        mrr = 0.8
        p50_ms = 12.0

    rec = RecallSuite(provider=lambda root, smoke: _Recall()).run(tmp_path)
    mem = MemorySuite(provider=lambda root, smoke: _Mem()).run(tmp_path)
    assert rec.status is GateStatus.MET and mem.status is GateStatus.MET

    class _MemBad:
        recall_at_5 = 0.5
        mrr = 0.4
        p50_ms = 12.0

    bad = MemorySuite(provider=lambda root, smoke: _MemBad()).run(tmp_path)
    assert bad.status is GateStatus.FAILED


def test_provider_ci_gates_are_honest_not_measured_without_providers(tmp_path: Path) -> None:
    """The two deferred provider-CI gates without their inputs are NOT_MEASURED — never
    a fake pass (Option A; VDM-008)."""
    runner = build_default_runner(RunnerConfig())  # no efficiency/recall provider
    for name in ("context-token-efficiency", "kg-retrieval-precision"):
        assert runner.run(name, tmp_path).status is GateStatus.NOT_MEASURED


def test_memory_usefulness_measures_provider_free_by_default() -> None:
    """memory-usefulness MEASURES via the deterministic seeded backend (VDM-008)."""
    runner = build_default_runner(RunnerConfig())  # no explicit memory provider
    report = runner.run("memory-usefulness", ".")
    assert report.status is GateStatus.MET, report.notes
    assert report.measured is True


def test_run_all_reports_carry_versioned_methodology() -> None:
    cfg = RunnerConfig(
        efficiency_provider=lambda root, smoke: EfficiencyReport(cases=[_case(True)]),
    )
    runner = build_default_runner(cfg)
    reports = runner.run_all(".")
    eff = next(r for r in reports if r.suite == "context-token-efficiency")
    assert eff.status is GateStatus.MET
    # Versioned-contract triad rides on every report (REL-12).
    assert eff.compatibility_version == "v1"
    assert all(r.version == "1.0.0" for r in reports)


def test_unknown_suite_raises() -> None:
    with pytest.raises(ValueError):
        BenchmarkRunner().run("nope", ".")
