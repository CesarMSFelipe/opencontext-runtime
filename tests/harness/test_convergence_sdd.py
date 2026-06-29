"""PR-004 SDD-CONV: handoff artifacts, strict scaffold blocking, meta-plan awareness."""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.agents.sdd_orchestrator import PHASE_ORDER
from opencontext_core.harness.artifact_store import ArtifactStore
from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.phases import _render_program_plan
from opencontext_core.harness.runner import HarnessRunner


def test_handoff_artifact_names_next_phase_inputs(tmp_path: Path) -> None:
    runner = HarnessRunner(root=tmp_path)
    result = runner.run("standard", "handoff demo", budget_mode=BudgetMode.OFF)

    run_dir = tmp_path / ".opencontext" / "runs" / result.run_id
    refs = ArtifactStore(run_dir).list_for_run(result.run_id)
    spec_handoffs = [
        r for r in refs if r.kind == "task-contract" and r.node_id == "spec"
    ]
    assert spec_handoffs, "expected a handoff artifact for the propose -> spec transition"
    payload = json.loads((run_dir / spec_handoffs[0].path).read_text(encoding="utf-8"))
    # The handoff names proposal.md as the spec phase's input.
    assert "proposal.md" in payload.get("open_questions", [])
    assert payload.get("to_persona") == "oc-requirements"


def test_strict_mode_blocks_a_scaffold_and_does_not_advance(tmp_path: Path) -> None:
    runner = HarnessRunner(root=tmp_path)
    runner._sdd_strict = True  # resolved from runtime.sdd_strict
    result = runner.run("sdd", "strict scaffold", budget_mode=BudgetMode.OFF)

    # The scaffolded propose phase FAILs the run and it does not advance to spec.
    assert result.status == GateStatus.FAILED
    run_dir = tmp_path / ".opencontext" / "runs" / result.run_id
    assert not (run_dir / "spec.md").exists()
    # propose did run (and was blocked), leaving its honest manifest behind.
    assert (run_dir / "propose-manifest.json").exists()


def test_program_plan_seeds_scope_and_preserves_phase_order(tmp_path: Path) -> None:
    from opencontext_core.planning.program import MetaPlanner

    plan = MetaPlanner().build(
        intent="Add a graph health command to the CLI",
        requirements=["REQ-1", "REQ-2"],
        persist=False,
    )
    plan_path = tmp_path / ".opencontext" / "program-plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(plan.model_dump_json(), encoding="utf-8")

    runner = HarnessRunner(root=tmp_path)
    state = runner.create_run("sdd", "Add a graph health command to the CLI")
    # The program plan is consumed and seeds phase scope.
    assert state.program_plan is not None
    assert _render_program_plan(state.program_plan) != ""
    # The canonical nine-phase order is preserved (REQ-01 unaffected by the plan).
    resolved = runner.schedule_phases("sdd")
    assert resolved == PHASE_ORDER
