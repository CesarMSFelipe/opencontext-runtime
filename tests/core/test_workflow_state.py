"""WorkflowState projection — read-only derivation from OcNewRunState.

The 10 oc-new phases are the source of truth (oc_new/models.py:PhaseName).
WorkflowState is a *projection*, never an independent store. The projection
MUST NOT write to disk, mutate the source, or trigger any orchestration side
effect. Tests prove (a) every phase is projected, (b) projection is
side-effect free, (c) projection handles edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.oc_new.flow import OC_NEW_FLOW, PHASE_NAMES
from opencontext_core.oc_new.models import (
    ChangeIdentity,
    NextAction,
    OcNewRunState,
    PhaseState,
)
from opencontext_core.workflow.state import WorkflowState

ALL_PHASES = set(PHASE_NAMES)


def _make_run_state(tmp_path: Path) -> OcNewRunState:
    """Build a minimal OcNewRunState covering all 10 phases."""
    identity = ChangeIdentity.from_task("add-graph-health")
    phases = [
        PhaseState(
            name=p.name,
            status="passed" if idx < 3 else "pending",
            artifact_paths=[f"{p.name}.artifact.json"] if idx < 3 else [],
            warnings=["dummy-warning"] if idx == 1 else [],
        )
        for idx, p in enumerate(OC_NEW_FLOW)
    ]
    return OcNewRunState(
        identity=identity,
        task="add-graph-health",
        phases=phases,
        current_phase="design",
        next_action=NextAction(
            kind="spawn_subagent",
            phase="design",
            persona="oc-architect",
            instruction="Run oc-design as oc-architect.",
        ),
        blocked_reason=None,
    )


def test_project_from_returns_workflow_state(tmp_path: Path) -> None:
    run_state = _make_run_state(tmp_path)
    assert isinstance(WorkflowState.project_from(run_state), WorkflowState)


def test_project_from_covers_all_ten_phases(tmp_path: Path) -> None:
    """All 10 oc-new phases from PhaseName appear in the projection."""
    projected = WorkflowState.project_from(_make_run_state(tmp_path))
    assert {p.name for p in projected.phases} == ALL_PHASES
    assert len(projected.phases) == 10


def test_project_from_preserves_per_phase_status(tmp_path: Path) -> None:
    run_state = _make_run_state(tmp_path)
    by_name = {p.name: p for p in WorkflowState.project_from(run_state).phases}
    assert by_name["explore"].status == "passed"
    assert by_name["propose"].status == "passed"
    assert by_name["spec"].status == "passed"
    assert by_name["design"].status == "pending"
    assert by_name["apply"].status == "pending"


def test_project_from_preserves_identity_and_current_phase(tmp_path: Path) -> None:
    """Identity and current_phase come through unchanged."""
    run_state = _make_run_state(tmp_path)
    projected = WorkflowState.project_from(run_state)
    assert projected.run_id == run_state.identity.run_id
    assert projected.change_id == run_state.identity.change_id
    assert projected.task == run_state.task
    assert projected.current_phase == run_state.current_phase
    assert projected.next_action_kind == "spawn_subagent"
    assert projected.blocked_reason is None


def test_project_from_is_side_effect_free(tmp_path: Path) -> None:
    """project_from() MUST NOT write to disk, mutate the source, or create files."""
    run_state = _make_run_state(tmp_path)
    before_files = set(tmp_path.rglob("*"))
    before_runs_dir = tmp_path / ".opencontext" / "runs"
    before_exists = before_runs_dir.exists()

    projected = WorkflowState.project_from(run_state)

    after_files = set(tmp_path.rglob("*"))
    assert after_files == before_files, "project_from must not write any new files"
    assert before_runs_dir.exists() == before_exists
    assert run_state.current_phase == "design", "source run_state must not be mutated"
    assert projected is not run_state  # type: ignore[comparison-overlap]
    # ponytail: one extra assertion, no fixture pollution checks via fixture.


@pytest.mark.parametrize(
    "mutator, expected_attr, expected_value",
    [
        (lambda s: s.model_copy(update={"next_action": None}), "next_action_kind", None),
        (
            lambda s: s.model_copy(
                update={"blocked_reason": "missing artifacts: spec.md", "current_phase": "spec"}
            ),
            "blocked_reason",
            "missing artifacts: spec.md",
        ),
        (
            lambda s: s.model_copy(
                update={"blocked_reason": "missing artifacts: spec.md", "current_phase": "spec"}
            ),
            "current_phase",
            "spec",
        ),
        (lambda s: s, ("explore", "artifact_paths"), ["explore.artifact.json"]),
        (lambda s: s, ("propose", "warnings"), ["dummy-warning"]),
    ],
)
def test_project_from_propagates_field(
    tmp_path: Path, mutator, expected_attr, expected_value
) -> None:
    """Triangulation: each field round-trips through the projection."""
    run_state = mutator(_make_run_state(tmp_path))
    projected = WorkflowState.project_from(run_state)
    if isinstance(expected_attr, tuple):
        phase_name, attr = expected_attr
        by_name = {p.name: p for p in projected.phases}
        assert getattr(by_name[phase_name], attr) == expected_value
    else:
        assert getattr(projected, expected_attr) == expected_value


def test_project_from_serialisable_to_json(tmp_path: Path) -> None:
    """Projection round-trips through JSON for UI/CLI consumption."""
    projected = WorkflowState.project_from(_make_run_state(tmp_path))
    blob = projected.model_dump_json()
    for name in ALL_PHASES:
        assert name in blob
    parsed = json.loads(blob)
    assert "phases" in parsed
    assert len(parsed["phases"]) == 10


def test_project_from_missing_canonical_phase_raises(tmp_path: Path) -> None:
    """A run state missing a canonical phase fails projection loudly."""
    run_state = _make_run_state(tmp_path)
    truncated = run_state.model_copy(update={"phases": run_state.phases[:-1]})
    with pytest.raises(ValueError):
        WorkflowState.project_from(truncated)