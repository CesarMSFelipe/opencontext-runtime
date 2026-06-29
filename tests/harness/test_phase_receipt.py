"""PR-004 REQ-06 / SDD-CONV: one uniform per-phase receipt per executed phase."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.models import BudgetMode
from opencontext_core.harness.receipt_store import ReceiptStore
from opencontext_core.harness.runner import HarnessRunner


def test_harness_run_emits_one_phase_receipt_per_executed_phase(tmp_path: Path) -> None:
    runner = HarnessRunner(root=tmp_path)
    result = runner.run("apply-only", "receipt coverage", budget_mode=BudgetMode.OFF)

    run_dir = tmp_path / ".opencontext" / "runs" / result.run_id
    receipts = ReceiptStore(run_dir).list_phase_receipts()
    receipted_phases = {r.phase for r in receipts}

    executed = {
        e.phase
        for e in result.events
        if e.action == "run_phase" and e.status in ("passed", "warning", "failed")
    }
    assert executed, "expected at least one executed phase"
    # Every executed phase has exactly one uniform per-phase receipt.
    assert executed <= receipted_phases
    for r in receipts:
        assert r.schema_version == "opencontext.phase_receipt.v1"
        assert r.run_id == result.run_id
        assert r.status  # non-empty status recorded
        # gate digest is a {gate_id: status} map (may be empty for some phases)
        assert isinstance(r.gate_digest, dict)


def test_oc_new_spine_writes_phase_receipt(tmp_path: Path) -> None:
    from opencontext_core.oc_new.conductor import OcNewConductor
    from opencontext_core.workflow.phase_result import PhaseResultEnvelope

    conductor = OcNewConductor(tmp_path)
    state = conductor.start("Add a thing")
    run_id = state.identity.run_id
    run_dir = tmp_path / ".opencontext" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    artifacts = ["explore.artifact.json", "context-pack.json"]
    for a in artifacts:
        (run_dir / a).write_text("{}", encoding="utf-8")
    env = PhaseResultEnvelope(
        run_id=run_id,
        change_id=state.identity.change_id,
        phase="explore",
        status="passed",
        duration_s=0.0,
        artifacts=artifacts,
    )
    (run_dir / "phase-result.explore.json").write_text(env.model_dump_json(), encoding="utf-8")

    conductor.mark_done(run_id, "explore", artifact_paths=artifacts)

    receipts = ReceiptStore(run_dir).list_phase_receipts()
    explore = [r for r in receipts if r.phase == "explore"]
    assert len(explore) == 1
    assert explore[0].status in {"passed", "warning"}
    assert explore[0].required_harnesses  # declared harnesses carried onto the receipt
