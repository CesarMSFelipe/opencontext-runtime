"""R5: OcNewConductor respects sdd_strict (tdd_mode='strict') before apply.

When AgenticFlowConfig.tdd_mode == 'strict', the conductor must block the
apply phase unless failing_test.json exists in the run directory.

Failing tests:
- strict on + no failing_test.json → next_action.kind == 'blocked'.
- strict on + failing_test.json present → proceeds (spawn_subagent or later).
- strict off → proceeds regardless.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.agentic.config import AgenticFlowConfig
from opencontext_core.oc_new.conductor import OcNewConductor
from opencontext_core.oc_new.flow import OC_NEW_FLOW
from opencontext_core.oc_new.models import ChangeIdentity, OcNewRunState, PhaseState


def _make_pre_apply_state(
    tmp_path: Path,
    *,
    tdd_mode: str = "ask",
) -> tuple[OcNewConductor, OcNewRunState, str]:
    """Build conductor + state where all phases before 'apply' are passed."""
    config = AgenticFlowConfig(tdd_mode=tdd_mode)  # type: ignore[call-arg]
    conductor = OcNewConductor(root=tmp_path)

    pre_apply = {"explore", "propose", "spec", "design", "tasks", "approval"}
    phases = [
        PhaseState(name=p.name, status="passed" if p.name in pre_apply else "pending")
        for p in OC_NEW_FLOW
    ]
    identity = ChangeIdentity.from_task("sdd-strict-test")
    state = OcNewRunState(
        identity=identity, task="sdd-strict-test", phases=phases, config=config
    )

    # Seed required artifacts for 'apply' so _missing_artifacts passes.
    run_dir = tmp_path / ".opencontext" / "runs" / identity.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    for artifact in ["approval.json", "tasks.md"]:
        (run_dir / artifact).write_text(
            json.dumps({"status": "approved"}), encoding="utf-8"
        )

    return conductor, state, identity.run_id


def test_strict_mode_blocks_apply_without_failing_test(tmp_path: Path) -> None:
    """strict on + no failing_test.json → conductor blocks at apply."""
    conductor, state, run_id = _make_pre_apply_state(tmp_path, tdd_mode="strict")

    result = conductor._advance(state)

    assert result.next_action is not None, "Expected a next_action"
    assert result.next_action.kind == "blocked", (
        f"Expected kind='blocked', got {result.next_action.kind!r}.\n"
        f"instruction: {result.next_action.instruction!r}"
    )
    assert result.next_action.phase == "apply", (
        f"Expected phase='apply', got {result.next_action.phase!r}"
    )
    # The block reason must name the missing evidence honestly
    instruction = result.next_action.instruction or ""
    assert "strict" in instruction.lower() or "failing" in instruction.lower() or "test" in instruction.lower(), (
        f"Expected honest TDD block reason. Got: {instruction!r}"
    )


def test_strict_mode_proceeds_when_failing_test_present(tmp_path: Path) -> None:
    """strict on + failing_test.json exists → conductor advances past the block."""
    conductor, state, run_id = _make_pre_apply_state(tmp_path, tdd_mode="strict")

    # Seed the failing test evidence file
    run_dir = tmp_path / ".opencontext" / "runs" / run_id
    (run_dir / "failing_test.json").write_text(
        json.dumps({"test": "test_foo", "status": "failing"}), encoding="utf-8"
    )

    result = conductor._advance(state)

    # Must NOT be blocked at apply — either spawn_subagent or a later phase
    assert result.next_action is not None
    assert result.next_action.kind != "blocked" or result.next_action.phase != "apply", (
        "Expected advance past apply block when failing_test.json is present.\n"
        f"Got kind={result.next_action.kind!r}, phase={result.next_action.phase!r}"
    )


def test_non_strict_mode_proceeds_without_failing_test(tmp_path: Path) -> None:
    """tdd_mode='ask' (default) → conductor is not blocked at apply."""
    conductor, state, run_id = _make_pre_apply_state(tmp_path, tdd_mode="ask")

    result = conductor._advance(state)

    # Should not be blocked at apply for non-strict mode
    if result.next_action is not None and result.next_action.kind == "blocked":
        assert result.next_action.phase != "apply", (
            "Non-strict mode must not block at apply phase due to missing failing_test.json.\n"
            f"Got: {result.next_action!r}"
        )
