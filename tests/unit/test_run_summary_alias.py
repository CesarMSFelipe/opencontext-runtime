"""TDD — C13: write stable run-summary.md alias at artifacts root.

RED gate: node_consolidation currently only writes consolidation/summary.md.
The tests assert run-summary.md exists at the artifacts root (same level as
the consolidation/ subdirectory), which fails until nodes.py:905 is updated.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.nodes import (
    DeterministicNodeExecutor,
    OCFlowContext,
    node_consolidation,
    node_gather_context,
    node_plan,
)


def _ctx(root: Path, artifacts: Path) -> OCFlowContext:
    artifacts.mkdir(parents=True, exist_ok=True)
    return OCFlowContext(
        root=root,
        artifacts_dir=artifacts,
        task="Summarize the project",
        lane=Lane.FAST,
        profile="balanced",
        executor=DeterministicNodeExecutor(),
        max_attempts=2,
        seed_paths=[],
    )


def test_run_summary_md_present_at_stable_path(tmp_path: Path) -> None:
    """run-summary.md must exist at the artifacts root after node_consolidation."""
    artifacts = tmp_path / "artifacts" / "oc-flow"
    ctx = _ctx(tmp_path, artifacts)
    node_gather_context(ctx)
    node_plan(ctx)
    node_consolidation(ctx)

    alias_path = ctx.artifacts_dir / "run-summary.md"
    assert alias_path.exists(), (
        f"run-summary.md must exist at {alias_path}. Only consolidation/summary.md was written."
    )


def test_run_summary_md_same_content_as_consolidation_summary(tmp_path: Path) -> None:
    """run-summary.md must have identical content to consolidation/summary.md."""
    artifacts = tmp_path / "artifacts" / "oc-flow"
    ctx = _ctx(tmp_path, artifacts)
    node_gather_context(ctx)
    node_plan(ctx)
    node_consolidation(ctx)

    alias_path = ctx.artifacts_dir / "run-summary.md"
    canonical_path = ctx.artifacts_dir / "consolidation" / "summary.md"

    assert canonical_path.exists(), "consolidation/summary.md must still be written"
    assert alias_path.read_text(encoding="utf-8") == canonical_path.read_text(encoding="utf-8"), (
        "run-summary.md must have identical content to consolidation/summary.md"
    )


def test_run_summary_md_path_consistent_across_two_runs(tmp_path: Path) -> None:
    """run-summary.md path is consistent across different runs."""
    paths_seen: list[Path] = []
    for run_idx in range(2):
        run_artifacts = tmp_path / f"run{run_idx}" / "artifacts" / "oc-flow"
        ctx = _ctx(tmp_path, run_artifacts)
        node_gather_context(ctx)
        node_plan(ctx)
        node_consolidation(ctx)
        alias = ctx.artifacts_dir / "run-summary.md"
        assert alias.exists(), f"run-summary.md missing for run {run_idx}"
        paths_seen.append(alias)

    # Both aliases should be under their respective artifacts_dir roots
    assert paths_seen[0].name == "run-summary.md"
    assert paths_seen[1].name == "run-summary.md"
    assert paths_seen[0] != paths_seen[1], "Each run should have its own run-summary.md"
