"""OC Flow escalation + consolidation tests (PR-007, FLOW-13, FLOW-14)."""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.oc_flow.models import InspectionReport, Lane
from opencontext_core.oc_flow.nodes import (
    DeterministicNodeExecutor,
    OCFlowContext,
    make_apply_edit,
    node_consolidation,
    node_escalation,
    node_gather_context,
    node_local_inspection,
    node_mutate,
    node_plan,
)


def _ctx(root: Path, edits: list | None = None) -> OCFlowContext:
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
    )


def test_escalation_emits_handoff_and_owner_candidates(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    ctx.inspection = InspectionReport(
        outcome="failed_blocking", failure_summary="cannot converge", llm_tokens=0
    )
    ctx.changed_files = ["pkg/mod.py"]
    result = node_escalation(ctx)

    report_path = ctx.artifacts_dir / "escalation" / "escalation-report.json"
    handoff_path = ctx.artifacts_dir / "escalation" / "handoff.md"
    assert report_path.exists()
    assert handoff_path.exists()
    report = json.loads(report_path.read_text())
    assert report["owner_candidates"]
    assert result.outputs["owner_candidates"]


def test_escalation_does_not_mutate_code(tmp_path: Path) -> None:
    target = tmp_path / "untouched.py"
    target.write_text("v = 1\n", encoding="utf-8")
    ctx = _ctx(tmp_path)
    ctx.inspection = InspectionReport(
        outcome="failed_blocking", failure_summary="blocked", llm_tokens=0
    )
    before = target.read_text()
    node_escalation(ctx)
    assert target.read_text() == before
    assert ctx.changed_files == []


def test_consolidation_writes_deltas_and_summary(tmp_path: Path) -> None:
    edit = make_apply_edit(
        "changed.py", content="x = 1\n", reason="add", requirement_ref="task addressed"
    )
    ctx = _ctx(tmp_path, [edit])
    node_gather_context(ctx)
    node_plan(ctx)
    node_mutate(ctx)
    node_local_inspection(ctx)
    node_consolidation(ctx)

    base = ctx.artifacts_dir / "consolidation"
    assert (base / "memory-delta.json").exists()
    assert (base / "graph-delta.json").exists()
    assert (base / "summary.md").exists()


def test_consolidation_reindexes_changed_file(tmp_path: Path) -> None:
    edit = make_apply_edit(
        "reindexed.py", content="y = 2\n", reason="add", requirement_ref="task addressed"
    )
    ctx = _ctx(tmp_path, [edit])
    node_gather_context(ctx)
    node_plan(ctx)
    node_mutate(ctx)
    node_local_inspection(ctx)
    node_consolidation(ctx)

    graph_delta = json.loads(
        (ctx.artifacts_dir / "consolidation" / "graph-delta.json").read_text()
    )
    assert "reindexed.py" in graph_delta["reindexed_files"]


def test_consolidation_does_not_save_chain_of_thought(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    node_gather_context(ctx)
    node_plan(ctx)
    node_mutate(ctx)
    node_local_inspection(ctx)
    node_consolidation(ctx)
    memory_delta = json.loads(
        (ctx.artifacts_dir / "consolidation" / "memory-delta.json").read_text()
    )
    assert memory_delta["saved_chain_of_thought"] is False
