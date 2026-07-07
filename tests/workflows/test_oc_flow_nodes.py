"""OC Flow node-contract tests (PR-007, FLOW-3, FLOW-7, FLOW-8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.harness.checkpoint import CheckpointStore
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.nodes import (
    DeterministicNodeExecutor,
    OCFlowContext,
    can_exit_gather_context,
    can_exit_init,
    make_apply_edit,
    node_gather_context,
    node_init,
    node_local_inspection,
    node_mutate,
    node_plan,
)


def _ctx(root: Path, *, edits: list | None = None) -> OCFlowContext:
    artifacts = root / "artifacts" / "oc-flow"
    artifacts.mkdir(parents=True, exist_ok=True)
    return OCFlowContext(
        root=root,
        artifacts_dir=artifacts,
        task="Fix failing test",
        lane=Lane.FAST,
        profile="balanced",
        executor=DeterministicNodeExecutor(requested_edits=edits or []),
        max_attempts=2,
        seed_paths=[],
    )


def test_gather_context_blocks_transition_without_envelope(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    # Before gather_context runs, no envelope exists -> exit refused (FLOW-3).
    assert ctx.envelope is None
    assert can_exit_gather_context(ctx) is False
    node_gather_context(ctx)
    assert ctx.envelope is not None
    assert can_exit_gather_context(ctx) is True


def test_init_exit_conditions_gate_gather_context(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    assert can_exit_init(ctx) is False
    node_init(ctx)
    assert can_exit_init(ctx) is True
    assert (ctx.artifacts_dir / "init.json").exists()
    assert (ctx.artifacts_dir / "workflow-selection.json").exists()


def test_mutate_edits_carry_reason_and_criterion_and_checkpoint(tmp_path: Path) -> None:
    edit = make_apply_edit(
        "mod_a.py", content="a = 1\n", reason="add a", requirement_ref="task addressed"
    )
    ctx = _ctx(tmp_path, edits=[edit])
    node_gather_context(ctx)
    node_plan(ctx)
    result = node_mutate(ctx)

    # FLOW-7: each applied edit had a reason + criterion ref, and a checkpoint exists.
    assert result.outputs["edits"] == 1
    receipts = (ctx.artifacts_dir / "apply-receipts.json").read_text()
    assert "mod_a.py" in receipts
    assert ctx.checkpoint_id and ctx.checkpoint_id != "empty"
    # The rollback checkpoint is retrievable from the store.
    store_dir = tmp_path / ".opencontext" / "checkpoints" / ctx.checkpoint_id
    assert store_dir.is_dir()
    assert (tmp_path / "mod_a.py").read_text() == "a = 1\n"


def test_mutate_writes_a_patch_even_for_noop(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)  # no edits
    node_gather_context(ctx)
    node_plan(ctx)
    node_mutate(ctx)
    assert (ctx.artifacts_dir / "patch.diff").exists()
    assert (ctx.artifacts_dir / "apply-receipts.json").exists()


def test_local_inspection_zero_llm_and_typed_outcome(tmp_path: Path) -> None:
    edit = make_apply_edit(
        "clean.py", content="ok = True\n", reason="add", requirement_ref="task addressed"
    )
    ctx = _ctx(tmp_path, edits=[edit])
    node_gather_context(ctx)
    node_plan(ctx)
    node_mutate(ctx)
    result = node_local_inspection(ctx)

    assert result.llm_tokens == 0
    assert ctx.inspection is not None
    assert ctx.inspection.llm_tokens == 0
    assert ctx.inspection.outcome in {
        "passed",
        "failed_recoverable",
        "failed_blocking",
        "skipped_with_reason",
    }
    assert ctx.inspection.outcome == "passed"


def test_local_inspection_flags_syntax_error_as_recoverable(tmp_path: Path) -> None:
    bad = make_apply_edit(
        "broken.py", content="def f(:\n", reason="bug", requirement_ref="task addressed"
    )
    ctx = _ctx(tmp_path, edits=[bad])
    node_gather_context(ctx)
    node_plan(ctx)
    node_mutate(ctx)
    node_local_inspection(ctx)
    assert ctx.inspection is not None
    assert ctx.inspection.outcome == "failed_recoverable"


def test_local_inspection_flags_secret_as_blocking(tmp_path: Path) -> None:
    leak = make_apply_edit(
        "leak.py",
        content='SECRET = "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"\n',
        reason="leak",
        requirement_ref="task addressed",
    )
    ctx = _ctx(tmp_path, edits=[leak])
    node_gather_context(ctx)
    node_plan(ctx)
    node_mutate(ctx)
    node_local_inspection(ctx)
    assert ctx.inspection is not None
    assert ctx.inspection.outcome == "failed_blocking"


def test_checkpoint_restore_reverts_mutation(tmp_path: Path) -> None:
    target = tmp_path / "exists.py"
    target.write_text("original = 1\n", encoding="utf-8")
    store = CheckpointStore(tmp_path)
    cp = store.create([target], source="test")
    assert cp is not None
    target.write_text("changed = 2\n", encoding="utf-8")
    cp.restore()
    assert target.read_text() == "original = 1\n"


@pytest.fixture(autouse=True)
def _legacy_local_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """This module asserts the legacy in-repo layout; pin local storage mode."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
