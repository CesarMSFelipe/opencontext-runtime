"""OC Flow run-bundle gates: evaluation, enforcement, and manifest writing.

Unit tests for the pure gate evaluation + status enforcement used to persist
run.json / gates.json / verification.json for OC Flow runs (AC-025).
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.oc_flow.run_bundle import (
    enforce_gates,
    evaluate_oc_flow_gates,
    write_run_bundle,
)

_REQUIRED_GATE_IDS = {
    "workspace_valid",
    "config_valid",
    "context_pack_created",
    "executor_available",
    "tdd_red_proven_if_strict",
    "tdd_functional_change_if_required",
    "mutation_performed_if_required",
    "verification_executed",
    "verification_passed",
    "report_written",
}


def _by_id(gates: list[dict]) -> dict[str, dict]:
    return {str(g["id"]): g for g in gates}


def test_gate_catalog_is_complete() -> None:
    gates = evaluate_oc_flow_gates(
        workspace_valid=True,
        config_valid=True,
        context_pack_created=True,
        executor_available=True,
        tdd_red_proven_if_strict=None,
        mutation_performed_if_required=True,
        verification_executed=True,
        verification_passed=True,
    )
    assert {g["id"] for g in gates} == _REQUIRED_GATE_IDS
    for gate in gates:
        assert gate["phase"] == "oc-flow"
        assert gate["status"] in {"passed", "failed", "skipped"}


def test_none_inputs_are_skipped_not_failed() -> None:
    gates = _by_id(
        evaluate_oc_flow_gates(
            workspace_valid=True,
            config_valid=True,
            context_pack_created=None,
            executor_available=None,
            tdd_red_proven_if_strict=None,
            mutation_performed_if_required=None,
            verification_executed=None,
            verification_passed=None,
        )
    )
    for gate_id in (
        "context_pack_created",
        "executor_available",
        "tdd_red_proven_if_strict",
        "mutation_performed_if_required",
        "verification_executed",
        "verification_passed",
    ):
        assert gates[gate_id]["status"] == "skipped", gate_id


def test_false_inputs_fail_their_gates() -> None:
    gates = _by_id(
        evaluate_oc_flow_gates(
            workspace_valid=False,
            config_valid=False,
            context_pack_created=False,
            executor_available=False,
            tdd_red_proven_if_strict=False,
            tdd_functional_change_if_required=False,
            mutation_performed_if_required=False,
            verification_executed=False,
            verification_passed=False,
        )
    )
    for gate_id in _REQUIRED_GATE_IDS - {"report_written"}:
        assert gates[gate_id]["status"] == "failed", gate_id


def test_enforcement_downgrades_completed_on_failed_gate() -> None:
    gates = evaluate_oc_flow_gates(
        workspace_valid=True,
        config_valid=True,
        context_pack_created=True,
        executor_available=True,
        tdd_red_proven_if_strict=False,  # strict RED gate failed
        mutation_performed_if_required=True,
        verification_executed=True,
        verification_passed=True,
    )
    assert enforce_gates("completed", gates) == "blocked"


def test_enforcement_keeps_clean_completed() -> None:
    gates = evaluate_oc_flow_gates(
        workspace_valid=True,
        config_valid=True,
        context_pack_created=True,
        executor_available=True,
        tdd_red_proven_if_strict=None,
        mutation_performed_if_required=True,
        verification_executed=True,
        verification_passed=True,
    )
    assert enforce_gates("completed", gates) == "completed"


def test_enforcement_leaves_non_completed_statuses_alone() -> None:
    gates = evaluate_oc_flow_gates(
        workspace_valid=True,
        config_valid=True,
        context_pack_created=True,
        executor_available=False,
        tdd_red_proven_if_strict=None,
        mutation_performed_if_required=False,
        verification_executed=None,
        verification_passed=None,
    )
    assert enforce_gates("needs_executor", gates) == "needs_executor"
    assert enforce_gates("escalated", gates) == "escalated"


def test_write_run_bundle_persists_manifest_gates_and_verification(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-x"
    manifest = {"run_id": "run-x", "workflow": "oc-flow", "status": "completed"}
    gates = evaluate_oc_flow_gates(
        workspace_valid=True,
        config_valid=True,
        context_pack_created=True,
        executor_available=True,
        tdd_red_proven_if_strict=None,
        mutation_performed_if_required=True,
        verification_executed=True,
        verification_passed=True,
    )
    write_run_bundle(
        run_dir,
        manifest=manifest,
        gates=gates,
        verification={"commands": ["pytest -q"], "outcome": "passed"},
        patch_text="--- a/app.py\n+++ b/app.py\n@@\n-x\n+y\n",
    )
    assert json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["run_id"] == "run-x"
    persisted = json.loads((run_dir / "gates.json").read_text(encoding="utf-8"))["gates"]
    assert {g["id"] for g in persisted} == _REQUIRED_GATE_IDS
    verification = json.loads((run_dir / "verification.json").read_text(encoding="utf-8"))
    assert verification["outcome"] == "passed"
    assert (run_dir / "mutations.diff").read_text(encoding="utf-8").startswith("--- a/app.py")


def test_write_run_bundle_omits_diff_when_no_edits(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-y"
    write_run_bundle(
        run_dir,
        manifest={"run_id": "run-y"},
        gates=[],
        verification={},
        patch_text=None,
    )
    assert (run_dir / "run.json").is_file()
    assert not (run_dir / "mutations.diff").exists()
