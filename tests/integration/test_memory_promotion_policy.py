"""TDD — C11: route durable_notes through MemoryPromotionPolicyV2.

RED gate: node_consolidation currently writes durable_notes unconditionally.
The test asserts that a generic no-op run records "not_promoted" in
memory-delta.json, which will fail until nodes.py:881-883 is updated.
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.nodes import (
    DeterministicNodeExecutor,
    OCFlowContext,
    node_consolidation,
    node_gather_context,
    node_plan,
)


def _ctx(root: Path) -> OCFlowContext:
    artifacts = root / "artifacts" / "oc-flow"
    artifacts.mkdir(parents=True, exist_ok=True)
    return OCFlowContext(
        root=root,
        artifacts_dir=artifacts,
        task="Generic no-op task: describe the project structure",
        lane=Lane.FAST,
        profile="balanced",
        executor=DeterministicNodeExecutor(),
        max_attempts=2,
        seed_paths=[],
    )


def test_generic_run_records_not_promoted(tmp_path: Path) -> None:
    """A generic no-op run must record promotion=not_promoted in memory-delta.json.

    Composite score for a no-op run = 0.0 (no changed files, no inspection
    outcome), which is below the keep threshold (0.6). evaluate_promotion returns
    REJECT, so durable_notes are NOT written and promotion="not_promoted" is set.
    """
    ctx = _ctx(tmp_path)
    node_gather_context(ctx)
    node_plan(ctx)
    node_consolidation(ctx)

    delta_path = ctx.artifacts_dir / "consolidation" / "memory-delta.json"
    assert delta_path.exists(), "memory-delta.json must be written by node_consolidation"

    delta = json.loads(delta_path.read_text(encoding="utf-8"))
    assert delta.get("promotion") == "not_promoted", (
        f"Expected promotion='not_promoted' in memory-delta.json but got: {delta}"
    )


def test_not_promoted_run_has_no_durable_notes(tmp_path: Path) -> None:
    """When a run is not promoted, durable_notes must NOT appear in memory-delta.json."""
    ctx = _ctx(tmp_path)
    node_gather_context(ctx)
    node_plan(ctx)
    node_consolidation(ctx)

    delta_path = ctx.artifacts_dir / "consolidation" / "memory-delta.json"
    delta = json.loads(delta_path.read_text(encoding="utf-8"))

    # durable_notes should be absent or empty for a not-promoted run
    assert not delta.get("durable_notes"), (
        f"Unexpected durable_notes in a not-promoted run: {delta.get('durable_notes')}"
    )
