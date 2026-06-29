"""OC Flow resume + first-run CLI tests (PR-007, FLOW-15, FLOW-16)."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.oc_flow.cli import run_oc_flow_cli
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.nodes import OCFlowError, make_apply_edit
from opencontext_core.oc_flow.runner import OCFlowRunner


def _run_with_diagnosis(tmp_path: Path) -> tuple[OCFlowRunner, object]:
    """Run a flow whose edit introduces a syntax bug so diagnosis attempts exist."""
    bad = make_apply_edit(
        "buggy.py", content="def f(:\n", reason="bug", requirement_ref="task addressed"
    )
    runner = OCFlowRunner(root=tmp_path)
    result = runner.run(
        "Fix failing test", lane=Lane.CAREFUL, profile="balanced", requested_edits=[bad]
    )
    return runner, result


def test_resume_restores_contract_and_attempts(tmp_path: Path) -> None:
    runner, result = _run_with_diagnosis(tmp_path)
    assert result.diagnosis_attempts >= 1
    resumed = runner.resume(result.session_id, result.run_id)
    assert resumed.contract.scope == "Fix failing test"
    assert len(resumed.diagnosis_attempts) == result.diagnosis_attempts
    assert resumed.inspection is not None
    assert resumed.patch  # patch state restored
    assert resumed.state["status"] == result.status


def test_resume_fails_safe_on_missing_required_artifact(tmp_path: Path) -> None:
    runner, result = _run_with_diagnosis(tmp_path)
    contract_path = result.artifacts_dir / "task-contract.json"
    contract_path.unlink()
    with pytest.raises(OCFlowError):
        runner.resume(result.session_id, result.run_id)


def test_run_to_completion_persists_artifacts(tmp_path: Path) -> None:
    edit = make_apply_edit(
        "fix.py", content="ok = 1\n", reason="add", requirement_ref="task addressed"
    )
    result = OCFlowRunner(root=tmp_path).run(
        "Fix failing test", lane=Lane.FAST, requested_edits=[edit]
    )
    assert result.status == "completed"
    assert result.final_node == "completed"
    ad = result.artifacts_dir
    assert (ad / "task-contract.json").exists()
    assert (ad / "patch.diff").exists()
    assert (ad / "inspection-report.json").exists()


def test_cli_run_workflow_oc_flow_needs_executor_on_noop_mutation(tmp_path: Path) -> None:
    # B1/AVH-011: a mutation task run with no provider/executor MUST NOT report
    # `completed` (the audit bug). The honest status is `needs_executor`; artifacts
    # are still produced and the blocking reason is surfaced.
    summary = run_oc_flow_cli(
        "Fix failing test",
        root=tmp_path,
        workflow="oc-flow",
        enabled=True,
        as_json=False,
    )
    assert summary["status"] == "needs_executor"
    assert summary["workflow"] == "oc-flow"
    assert summary["completion_reason"]
    artifacts = Path(summary["artifacts_dir"])
    assert (artifacts / "task-contract.json").exists()
    assert (artifacts / "patch.diff").exists()
    assert (artifacts / "inspection-report.json").exists()


def test_cli_run_disabled_when_flag_off(tmp_path: Path) -> None:
    summary = run_oc_flow_cli("Fix failing test", root=tmp_path, workflow="oc-flow", enabled=False)
    assert summary["status"] == "disabled"


def test_run_is_no_longer_deprecated() -> None:
    from opencontext_cli.main import _build_parser, _DeprecationAwareParser

    assert "run" not in _DeprecationAwareParser._DEPRECATED
    parser = _build_parser()
    args = parser.parse_args(["run", "Fix failing test", "--workflow", "oc-flow"])
    assert args.command == "run"
    assert args.task == "Fix failing test"
    assert args.workflow == "oc-flow"
