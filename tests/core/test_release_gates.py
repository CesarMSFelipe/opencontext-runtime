"""Release DoD gates + the doc-57 1.0 acceptance verdict (REL-11, REL-CONV)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.evaluation.models import (
    BenchmarkSuiteReport,
    CostTriple,
    EfficiencyCaseResult,
    EfficiencyReport,
    GateStatus,
)
from opencontext_core.evaluation.runner import (
    MANDATORY_GATES,
    DeclaredSuite,
    RunnerConfig,
    build_default_runner,
)
from opencontext_core.operating_model.release_gate import (
    FUNCTIONAL_BEHAVIOURS,
    GOVERNANCE_GATES,
    AcceptanceEvaluator,
    GateResult,
    ReleaseBaselineStore,
    ReleaseGateRunner,
    ReleaseMetrics,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class _AlwaysMet(DeclaredSuite):
    """A suite stub that reports a genuine MET (for the all-green verdict test)."""

    def run(self, root: Path, *, smoke: bool = False) -> BenchmarkSuiteReport:
        return BenchmarkSuiteReport(
            suite=self.name, version="1.0.0", status=GateStatus.MET, measured=True, success=True
        )


# ── REL-11: the four DoD regression gates ─────────────────────────────────────


def test_first_run_seeds_baseline_and_passes() -> None:
    gates = ReleaseGateRunner().evaluate(ReleaseMetrics(median_tokens=100), None)
    assert {g.gate for g in gates} == {
        "no-first-run-regression",
        "no-benchmark-quality-regression",
        "no-uncontrolled-token-increase",
        "no-critical-policy-bypass",
    }
    assert all(g.status is GateStatus.MET for g in gates)


def test_token_increase_beyond_threshold_blocks() -> None:
    base = ReleaseMetrics(median_tokens=100)
    cur = ReleaseMetrics(median_tokens=130)
    gates = ReleaseGateRunner().evaluate(cur, base, token_threshold=0.10)
    token_gate = next(g for g in gates if g.gate == "no-uncontrolled-token-increase")
    assert token_gate.status is GateStatus.FAILED


def test_token_increase_within_threshold_passes() -> None:
    base = ReleaseMetrics(median_tokens=100)
    cur = ReleaseMetrics(median_tokens=105)
    gates = ReleaseGateRunner().evaluate(cur, base, token_threshold=0.10)
    token_gate = next(g for g in gates if g.gate == "no-uncontrolled-token-increase")
    assert token_gate.status is GateStatus.MET


def test_first_run_regression_blocks() -> None:
    base = ReleaseMetrics(first_run_success_rate=1.0)
    cur = ReleaseMetrics(first_run_success_rate=0.8)
    gates = ReleaseGateRunner().evaluate(cur, base)
    gate = next(g for g in gates if g.gate == "no-first-run-regression")
    assert gate.status is GateStatus.FAILED


def test_critical_policy_bypass_always_blocks() -> None:
    cur = ReleaseMetrics(critical_policy_bypasses=1)
    # Even on the very first (seeding) run, a critical bypass is never acceptable.
    gates = ReleaseGateRunner().evaluate(cur, None)
    gate = next(g for g in gates if g.gate == "no-critical-policy-bypass")
    assert gate.status is GateStatus.FAILED


def test_baseline_store_roundtrip(tmp_path: Path) -> None:
    store = ReleaseBaselineStore(tmp_path / "release-baseline.json")
    assert store.load() is None
    store.save(ReleaseMetrics(median_tokens=42))
    loaded = store.load()
    assert loaded is not None and loaded.median_tokens == 42


# ── doc-57 acceptance verdict (A ∧ B ∧ C ∧ D) ─────────────────────────────────


def test_acceptance_verdict_is_honestly_not_ready_today() -> None:
    verdict = AcceptanceEvaluator(repo_root=PROJECT_ROOT).evaluate()
    assert verdict.ready is False
    assert verdict.verdict == "not-ready"
    # Most gates are honestly NOT_MEASURED; nothing is fabricated as MET.
    assert verdict.not_measured > 0
    assert verdict.failed == 0
    met_gates = {g.gate for g in verdict.gates if g.status is GateStatus.MET}
    # The two genuinely self-checkable gates ARE measured and pass.
    assert "publish-uses-pypi-token-not-oidc" in met_gates
    assert "benchmark-methodology-versioned" in met_gates


def test_acceptance_covers_all_four_categories() -> None:
    verdict = AcceptanceEvaluator(repo_root=PROJECT_ROOT).evaluate()
    cats = {g.category for g in verdict.gates}
    assert cats == {"A", "B", "C", "D"}
    a_gates = {g.gate for g in verdict.gates if g.category == "A"}
    assert "first-run" in a_gates and "resume-rollback" in a_gates  # the ten gates


def test_acceptance_ready_only_when_every_gate_met() -> None:
    """Injecting MET evidence for everything makes the verdict ready (no-1.0 invariant)."""
    ok_case = EfficiencyCaseResult(
        case_id="c",
        con=CostTriple(tokens=1, tool_calls=1, latency_ms=1.0),
        sin=CostTriple(tokens=2, tool_calls=2, latency_ms=2.0),
        con_sufficient=True,
        source_coverage=1.0,
    )
    # All ten A gates MET: wire efficiency, and replace the rest with MET stand-ins.
    runner = build_default_runner(
        RunnerConfig(
            efficiency_provider=lambda r, s: EfficiencyReport(cases=[ok_case]),
            extra=[_AlwaysMet(name=n) for n in MANDATORY_GATES if n != "context-token-efficiency"],
        )
    )
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
    verdict = AcceptanceEvaluator(repo_root=PROJECT_ROOT, runner=runner).evaluate(
        functional=functional,
        regression=regression,
        governance=governance,
        dod_gates=dod,
        # AVH-010: the mandatory e2e-dod gate is MET when the DoD journey is proven.
        e2e_proof={"passed": True, "steps": [{"step": "all", "ok": True}]},
    )
    assert verdict.ready is True and verdict.failed == 0 and verdict.not_measured == 0


def test_a_single_failed_gate_keeps_verdict_not_ready() -> None:
    verdict = AcceptanceEvaluator(repo_root=PROJECT_ROOT).evaluate(
        regression={"suite-green": (GateStatus.FAILED, "a test failed")}
    )
    assert verdict.ready is False
    assert verdict.failed >= 1
