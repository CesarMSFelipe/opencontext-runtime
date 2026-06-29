"""PR-004 REQ-08: ProposePhase honesty parity with the sibling work phases."""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.phases import ProposePhase
from opencontext_core.harness.runner import HarnessRunner


class _OkDelegate:
    """Minimal delegate whose propose call returns a real narrative."""

    def delegate(self, phase: str, context: dict) -> object:
        return type(
            "R",
            (),
            {"status": "success", "output": f"Real {phase} narrative", "error": None},
        )()


def test_absent_executor_is_warning_with_manifest_and_warning(tmp_path: Path) -> None:
    runner = HarnessRunner(root=tmp_path)
    state = runner.create_run("sdd", "honest propose")
    assert state.delegate is None  # mock/zero-config: no real executor
    cfg = runner.config.phases.get("propose")
    result = ProposePhase(cfg, BudgetMode.OFF).run(state)

    # Honest non-pass (parity with spec/design/tasks), not a fabricated PASSED.
    assert result.status == GateStatus.WARNING
    # A guardrail gate surfaces the scaffold.
    assert any(g.id == "guardrails" for g in result.gates)
    # A phase manifest is written recording the planned (not completed) status.
    run_dir = tmp_path / ".opencontext" / "runs" / state.run_id
    manifest_path = run_dir / "propose-manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "planned"
    assert manifest["executor"] == "absent"
    # The "no model bound" warning is appended (matching SpecPhase).
    assert any("no model bound" in w for w in state.warnings)
    # The proposal artifact is marked as a scaffold so it cannot fake completion.
    proposal = json.loads((run_dir / "proposal.json").read_text(encoding="utf-8"))
    assert proposal["status"] == "planned"
    assert proposal.get("_scaffold") is True


def test_real_executor_is_passed_and_drafted(tmp_path: Path) -> None:
    runner = HarnessRunner(root=tmp_path)
    state = runner.create_run("sdd", "real propose")
    state.delegate = _OkDelegate()
    cfg = runner.config.phases.get("propose")
    result = ProposePhase(cfg, BudgetMode.OFF).run(state)

    assert result.status == GateStatus.PASSED
    run_dir = tmp_path / ".opencontext" / "runs" / state.run_id
    proposal = json.loads((run_dir / "proposal.json").read_text(encoding="utf-8"))
    assert proposal["status"] == "drafted"
    assert "_scaffold" not in proposal
    manifest = json.loads((run_dir / "propose-manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["executor"] == "real"


def test_strict_mode_fails_a_scaffold_proposal(tmp_path: Path) -> None:
    runner = HarnessRunner(root=tmp_path)
    state = runner.create_run("sdd", "strict propose")
    state.sdd_strict = True  # runtime.sdd_strict resolved onto the run state
    assert state.delegate is None
    cfg = runner.config.phases.get("propose")
    result = ProposePhase(cfg, BudgetMode.OFF).run(state)

    assert result.status == GateStatus.FAILED  # strict blocks a scaffold
    assert any(g.id == "guardrails" and g.status == GateStatus.FAILED for g in result.gates)
