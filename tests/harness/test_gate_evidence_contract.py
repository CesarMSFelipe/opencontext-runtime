"""Per-gate evidence invariant (HARNESS-CRIT-4).

DOC1 acceptance criterion: "each gate must carry evidence". The invariant lives
at the persistence boundary — every gate record written to ``gates.json`` (by
the harness runner and by the OC Flow run-bundle writer) must carry a non-empty
human-readable ``message``. See docs/product-contract/GATES_CONTRACT.md
§Evidence rule.
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.harness.models import (
    BudgetMode,
    GateStatus,
    HarnessRunResult,
    PhaseGate,
)
from opencontext_core.harness.runner import HarnessRunner
from opencontext_core.oc_flow.run_bundle import (
    evaluate_oc_flow_gates,
    write_run_bundle,
)


def _load_gates(run_dir: Path) -> list[dict]:
    payload = json.loads((run_dir / "gates.json").read_text(encoding="utf-8"))
    return list(payload["gates"])


def _assert_every_gate_has_evidence(gates: list[dict]) -> None:
    assert gates, "expected at least one persisted gate record"
    for gate in gates:
        message = gate.get("message")
        assert isinstance(message, str) and message.strip(), (
            f"gate '{gate.get('id')}' was persisted without an evidence message"
        )


def test_real_harness_run_persists_evidence_per_gate(tmp_path: Path) -> None:
    """HARNESS-CRIT-4: every gate record in gates.json from a real harness run
    carries a non-empty evidence message."""
    runner = HarnessRunner(root=tmp_path)
    result = runner.run("explore-only", "gate evidence probe", BudgetMode.OFF)

    run_dir = tmp_path / ".opencontext" / "runs" / result.run_id
    _assert_every_gate_has_evidence(_load_gates(run_dir))


def test_harness_persist_backfills_missing_gate_message(tmp_path: Path) -> None:
    """HARNESS-CRIT-4: persist_run never writes a gate record with an empty
    message — a gate recorded without evidence is backfilled with an honest
    fallback naming the gate id and its status."""
    runner = HarnessRunner(root=tmp_path)
    state = runner.create_run("sdd", "empty message gate")
    result = HarnessRunResult(
        run_id=state.run_id,
        workflow="sdd",
        task="empty message gate",
        status=GateStatus.PASSED,
        gates=[PhaseGate(id="custom_gate", phase="apply", status=GateStatus.PASSED)],
    )
    run_dir = runner.persist_run(state, result)

    gates = _load_gates(run_dir)
    _assert_every_gate_has_evidence(gates)
    record = next(g for g in gates if g["id"] == "custom_gate")
    assert "custom_gate" in record["message"]
    assert "passed" in record["message"]


def test_oc_flow_full_catalog_persists_evidence_per_gate(tmp_path: Path) -> None:
    """HARNESS-CRIT-4: the full OC Flow gate catalog persists a non-empty
    message per gate in gates.json across passed, failed, and skipped states."""
    run_dir = tmp_path / "run-evidence"
    gates = evaluate_oc_flow_gates(
        workspace_valid=True,
        config_valid=True,
        context_pack_created=True,
        executor_available=False,  # failed gate keeps its failure evidence
        tdd_red_proven_if_strict=None,  # skipped gate keeps its skip evidence
        mutation_performed_if_required=True,
        verification_executed=True,
        verification_passed=True,
    )
    write_run_bundle(
        run_dir,
        manifest={"run_id": "run-evidence", "workflow": "oc-flow", "status": "blocked"},
        gates=gates,
        verification={"commands": [], "outcome": "not_run"},
    )
    _assert_every_gate_has_evidence(_load_gates(run_dir))


def test_oc_flow_writer_backfills_missing_gate_message(tmp_path: Path) -> None:
    """HARNESS-CRIT-4: write_run_bundle never persists a gate record with an
    empty message — records handed in without evidence are backfilled with an
    honest fallback naming the gate id and its status."""
    run_dir = tmp_path / "run-backfill"
    write_run_bundle(
        run_dir,
        manifest={"run_id": "run-backfill", "workflow": "oc-flow", "status": "completed"},
        gates=[{"id": "custom_gate", "phase": "oc-flow", "status": "passed"}],
        verification={"commands": [], "outcome": "not_run"},
    )
    gates = _load_gates(run_dir)
    _assert_every_gate_has_evidence(gates)
    assert "custom_gate" in gates[0]["message"]
    assert "passed" in gates[0]["message"]
