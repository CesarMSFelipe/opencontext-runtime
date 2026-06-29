"""OC Flow no-op completion gate (B1 / AVH-011).

A mutation-required task that produced no verified change MUST NOT report
``completed``; a read-only task may. These tests pin the completion state machine
(``resolve_completion`` + ``mutation_required``) and the end-to-end runner behaviour.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.oc_flow.completion import (
    CompletionStatus,
    mutation_required,
    resolve_completion,
)
from opencontext_core.oc_flow.models import InspectionReport, Lane
from opencontext_core.oc_flow.nodes import (
    DeterministicNodeExecutor,
    OCFlowContext,
    make_apply_edit,
)
from opencontext_core.oc_flow.runner import OCFlowRunner


def _ctx(
    tmp_path: Path,
    *,
    changed: list[str] | None = None,
    inspection: InspectionReport | None = None,
    executor: object | None = None,
) -> OCFlowContext:
    artifacts = tmp_path / "artifacts" / "oc-flow"
    artifacts.mkdir(parents=True, exist_ok=True)
    ctx = OCFlowContext(
        root=tmp_path,
        artifacts_dir=artifacts,
        task="Fix failing test",
        lane=Lane.FAST,
        profile="balanced",
        executor=executor or DeterministicNodeExecutor(),
        max_attempts=2,
    )
    ctx.changed_files = changed or []
    ctx.inspection = inspection
    return ctx


# ----------------------------------------------------------- mutation_required classifier
def test_fix_task_is_mutation_required() -> None:
    assert mutation_required("Fix failing test") is True
    assert mutation_required("Implement the add function") is True
    assert mutation_required("Refactor the parser module") is True
    assert mutation_required("edit the config loader") is True


def test_readonly_task_is_not_mutation_required() -> None:
    assert mutation_required("Explain the runtime architecture") is False
    assert mutation_required("Review the logging setup") is False
    assert mutation_required("Analyze the call graph") is False
    assert mutation_required("Document the public API") is False


# --------------------------------------------------------------- resolve_completion unit
def test_readonly_noop_completes(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    status = resolve_completion("completed", ctx, mutation_required=False, provider_available=False)
    assert status is CompletionStatus.completed


def test_mutation_noop_deterministic_needs_executor(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, executor=DeterministicNodeExecutor())
    status = resolve_completion("completed", ctx, mutation_required=True, provider_available=False)
    assert status is CompletionStatus.needs_executor


def test_mutation_noop_provider_backed_but_empty_is_blocked(tmp_path: Path) -> None:
    # A productive (non-deterministic) executor that produced nothing is blocked,
    # not needs_executor (an executor exists; it just yielded no edits).
    class _Stub:
        provider_available = True

    ctx = _ctx(tmp_path, executor=_Stub())
    status = resolve_completion("completed", ctx, mutation_required=True, provider_available=True)
    assert status is CompletionStatus.blocked


def test_mutation_verified_change_completes(tmp_path: Path) -> None:
    passed = InspectionReport(outcome="passed", gate_results=[], failure_summary="")
    ctx = _ctx(tmp_path, changed=["fix.py"], inspection=passed)
    status = resolve_completion("completed", ctx, mutation_required=True, provider_available=False)
    assert status is CompletionStatus.completed


def test_escalated_graph_maps_to_escalated_for_readonly(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    status = resolve_completion("escalated", ctx, mutation_required=False, provider_available=False)
    assert status is CompletionStatus.escalated


# ------------------------------------------------------------------ end-to-end via runner
def test_failing_test_noop_run_not_completed(tmp_path: Path) -> None:
    # Seed a genuinely failing condition; with no provider the run must NOT complete
    # and must NOT fabricate a fix.
    (tmp_path / "buggy.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    result = OCFlowRunner(root=tmp_path).run("Fix failing test", lane=Lane.FAST)
    assert result.status != "completed"
    assert result.status == "needs_executor"
    assert result.mutation_required is True
    # The bug remained — no edits were produced.
    assert (tmp_path / "buggy.py").read_text() == "def add(a, b):\n    return a - b\n"


def test_empty_changed_files_mutation_blocked_with_reason(tmp_path: Path) -> None:
    result = OCFlowRunner(root=tmp_path).run("Refactor the parser", lane=Lane.FAST)
    assert result.status in {"needs_executor", "blocked", "escalated", "needs_provider"}
    assert result.completion_reason  # the receipt carries a blocking reason
    # The persisted run state records the honest status + reason.
    state = (result.artifacts_dir.parent.parent / "state.json").read_text(encoding="utf-8")
    assert result.status in state


def test_readonly_task_completes_with_no_edits(tmp_path: Path) -> None:
    result = OCFlowRunner(root=tmp_path).run("Explain the runtime architecture", lane=Lane.FAST)
    assert result.status == "completed"
    assert result.mutation_required is False
    assert result.graph_status == "completed"


def test_verified_mutation_completes_via_runner(tmp_path: Path) -> None:
    edit = make_apply_edit(
        "fix.py", content="ok = 1\n", reason="fix", requirement_ref="task addressed"
    )
    result = OCFlowRunner(root=tmp_path).run(
        "Fix failing test", lane=Lane.FAST, requested_edits=[edit]
    )
    assert result.status == "completed"
    assert result.mutation_required is True
    assert (tmp_path / "fix.py").exists()
