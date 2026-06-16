"""Config-driven gate dispatcher tests (, task 3.6).

HarnessRunner must dispatch the per-phase declared gates from config (running the
existing gate classes in harness/gates.py), not only the two hardcoded gates
(Confidence + Privacy).
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.config import HarnessConfig, PhaseConfig
from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.runner import HarnessRunner


def test_declared_security_scan_gate_runs_on_verify(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    cfg = HarnessConfig()
    cfg.phases["apply"] = PhaseConfig(budget_tokens=12000, gates=[])
    cfg.phases["verify"] = PhaseConfig(budget_tokens=4000, gates=["security_scan_passed"])
    runner = HarnessRunner(root=tmp_path, config=cfg)
    result = runner.run("apply-only", "dispatch task", BudgetMode.OFF)

    gate_ids = {g.id for g in result.gates}
    assert "security_scan_passed" in gate_ids


def test_undeclared_gate_does_not_run(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    cfg = HarnessConfig()
    # No phase declares no_high_risk_exports.
    for name, pc in cfg.phases.items():
        cfg.phases[name] = PhaseConfig(
            budget_tokens=pc.budget_tokens,
            gates=[g for g in pc.gates if g != "no_high_risk_exports"],
            confidence_threshold=pc.confidence_threshold,
            complexity=pc.complexity,
        )
    runner = HarnessRunner(root=tmp_path, config=cfg)
    result = runner.run("apply-only", "no high risk", BudgetMode.OFF)
    gate_ids = {g.id for g in result.gates}
    assert "no_high_risk_exports" not in gate_ids


def test_declared_no_high_risk_exports_gate_runs(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    cfg = HarnessConfig()
    cfg.phases["apply"] = PhaseConfig(
        budget_tokens=12000, gates=["no_high_risk_exports", "provider_policy_passed"]
    )
    runner = HarnessRunner(root=tmp_path, config=cfg)
    result = runner.run("apply-only", "exports task", BudgetMode.OFF)
    gate_ids = {g.id for g in result.gates}
    assert "no_high_risk_exports" in gate_ids
    assert "provider_policy_passed" in gate_ids
    # Both are PASSED by default (no external provider / no confidential export).
    for gid in ("no_high_risk_exports", "provider_policy_passed"):
        g = next(g for g in result.gates if g.id == gid)
        assert g.status == GateStatus.PASSED
