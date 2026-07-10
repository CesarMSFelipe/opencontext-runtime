"""VDM-006: the C/CI regression gates report MET/FAILED/NOT_MEASURED from real evidence.

* The five externally-measured CI gates (suite-green / gate-k / mypy / ruff /
  forbidden-names) read a ``ci-gates.json`` ``{gate: bool}`` map produced by the
  release-acceptance workflow.
* The mandatory ``e2e-dod`` gate reads the DoD proof artifact.
* The four DoD baseline-delta gates come from :class:`ReleaseGateRunner`.

Honesty (build-rule #1): a missing signal is NOT_MEASURED, never a fabricated pass.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.evaluation.models import GateStatus
from opencontext_core.operating_model.release_gate import (
    CI_GATES_PATH,
    AcceptanceEvaluator,
    ReleaseGateRunner,
    ReleaseMetrics,
    read_ci_gates,
    read_dod_proof,
    write_dod_proof,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CI_GATES = (
    "suite-green",
    "gate-k-12-12",
    "mypy-strict-clean",
    "ruff-clean",
    "forbidden-names-clean",
)


def _write_ci_gates(root: Path, mapping: dict[str, object]) -> None:
    path = root / CI_GATES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping), encoding="utf-8")


def _statuses(regression: dict[str, object]) -> dict[str, GateStatus]:
    verdict = AcceptanceEvaluator(repo_root=PROJECT_ROOT).evaluate(
        bench_root=str(PROJECT_ROOT), regression=regression or None
    )
    return {g.gate: g.status for g in verdict.gates}


def test_all_pass_ci_gates_report_met(tmp_path: Path) -> None:
    _write_ci_gates(tmp_path, {name: True for name in _CI_GATES})
    regression = read_ci_gates(tmp_path)
    statuses = _statuses(regression)
    for name in _CI_GATES:
        assert statuses[name] is GateStatus.MET, name


def test_failing_ci_entry_reports_failed_not_met(tmp_path: Path) -> None:
    mapping: dict[str, object] = {name: True for name in _CI_GATES}
    mapping["mypy-strict-clean"] = False
    _write_ci_gates(tmp_path, mapping)
    statuses = _statuses(read_ci_gates(tmp_path))
    assert statuses["mypy-strict-clean"] is GateStatus.FAILED
    assert statuses["ruff-clean"] is GateStatus.MET


def test_missing_ci_gates_file_keeps_all_not_measured(tmp_path: Path) -> None:
    assert read_ci_gates(tmp_path) == {}
    statuses = _statuses({})
    for name in _CI_GATES:
        assert statuses[name] is GateStatus.NOT_MEASURED, name


def test_dod_baseline_gates_met_with_seeded_metrics() -> None:
    # First run (baseline is None) seeds + passes the four DoD regression gates.
    gates = ReleaseGateRunner().evaluate(ReleaseMetrics(median_tokens=100), None)
    names = {g.gate for g in gates}
    assert names == {
        "no-first-run-regression",
        "no-benchmark-quality-regression",
        "no-uncontrolled-token-increase",
        "no-critical-policy-bypass",
    }
    assert all(g.status is GateStatus.MET for g in gates)


def test_dod_baseline_regression_blocks() -> None:
    base = ReleaseMetrics(first_run_success_rate=1.0, median_tokens=100)
    cur = ReleaseMetrics(first_run_success_rate=0.7, median_tokens=100)
    gates = ReleaseGateRunner().evaluate(cur, base)
    gate = next(g for g in gates if g.gate == "no-first-run-regression")
    assert gate.status is GateStatus.FAILED


@pytest.mark.slow
def test_e2e_dod_gate_met_from_proof_artifact(tmp_path: Path) -> None:
    write_dod_proof(tmp_path, passed=True, steps=[{"step": "all", "ok": True}])
    proof = read_dod_proof(tmp_path)
    assert proof is not None and proof["passed"] is True
    verdict = AcceptanceEvaluator(repo_root=tmp_path).evaluate(bench_root=str(tmp_path))
    e2e = next(g for g in verdict.gates if g.gate == "e2e-dod")
    assert e2e.status is GateStatus.MET
