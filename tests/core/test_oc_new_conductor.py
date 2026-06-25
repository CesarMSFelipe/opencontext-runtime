"""Tests for OcNewConductor."""

from __future__ import annotations

from opencontext_core.oc_new.conductor import OcNewConductor


def test_conductor_start_points_to_explore(tmp_path):
    conductor = OcNewConductor(tmp_path)
    state = conductor.start("Add graph health command")

    assert state.current_phase == "explore"
    assert state.next_action is not None
    assert state.next_action.kind == "spawn_subagent"
    assert state.next_action.phase == "explore"
    assert state.blocked_reason is None


def test_conductor_advances_after_phase_done(tmp_path):
    conductor = OcNewConductor(tmp_path)
    state = conductor.start("Add graph health command")

    run_dir = tmp_path / ".opencontext" / "runs" / state.identity.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "explore.artifact.json").write_text("{}", encoding="utf-8")

    state = conductor.mark_done(
        state.identity.run_id,
        "explore",
        artifact_paths=["explore.artifact.json"],
    )

    assert state.current_phase == "propose"
    assert state.next_action is not None
    assert state.next_action.kind == "spawn_subagent"


def test_conductor_blocks_when_artifact_missing(tmp_path):
    conductor = OcNewConductor(tmp_path)
    state = conductor.start("Add graph health command")

    # Mark explore done WITHOUT creating the artifact file
    state = conductor.mark_done(state.identity.run_id, "explore")

    # propose needs explore.artifact.json — should be blocked
    assert state.current_phase == "propose"
    assert state.next_action is not None
    assert state.next_action.kind == "blocked"
    assert "explore.artifact.json" in (state.blocked_reason or "")


def test_conductor_reaches_approval_phase(tmp_path):
    conductor = OcNewConductor(tmp_path)
    state = conductor.start("test")
    run_dir = tmp_path / ".opencontext" / "runs" / state.identity.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Drive through explore -> propose -> spec -> design -> tasks
    artifacts_by_phase = {
        "explore": ["explore.artifact.json"],
        "propose": ["proposal.md", "proposal.json", "propose.artifact.json"],
        "spec": ["spec.md", "spec.json", "spec.artifact.json"],
        "design": ["design.md", "design.json", "design.artifact.json"],
        "tasks": ["tasks.md", "tasks.json", "tasks.artifact.json"],
    }
    for phase_name, artifacts in artifacts_by_phase.items():
        for a in artifacts:
            (run_dir / a).write_text("{}", encoding="utf-8")
        state = conductor.mark_done(state.identity.run_id, phase_name, artifact_paths=artifacts)

    assert state.current_phase == "approval"
    assert state.next_action is not None
    assert state.next_action.kind == "request_approval"


def test_conductor_resume(tmp_path):
    conductor = OcNewConductor(tmp_path)
    state = conductor.start("Add graph health command")
    run_id = state.identity.run_id

    resumed = conductor.resume(run_id)
    assert resumed.current_phase == "explore"
    assert resumed.identity.run_id == run_id


def test_conductor_state_persisted(tmp_path):
    conductor = OcNewConductor(tmp_path)
    state = conductor.start("My task")
    run_id = state.identity.run_id

    loaded = conductor.store.load(run_id)
    assert loaded.task == "My task"
    assert loaded.identity.run_id == run_id


def test_mark_done_reads_artifacts_from_envelope_file(tmp_path):
    """When phase-result.<phase>.json exists, its artifacts field is used."""

    from opencontext_core.workflow.phase_result import PhaseResultEnvelope

    conductor = OcNewConductor(tmp_path)
    state = conductor.start("test envelope read")
    run_dir = tmp_path / ".opencontext" / "runs" / state.identity.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Write both the expected artifact and the phase-result envelope
    (run_dir / "explore.artifact.json").write_text("{}", encoding="utf-8")
    (run_dir / "context-pack.json").write_text("{}", encoding="utf-8")
    envelope = PhaseResultEnvelope(
        run_id=state.identity.run_id,
        change_id=state.identity.change_id,
        phase="explore",
        status="passed",
        duration_s=0.1,
        artifacts=["explore.artifact.json", "context-pack.json"],
    )
    (run_dir / "phase-result.explore.json").write_text(envelope.model_dump_json(), encoding="utf-8")

    new_state = conductor.mark_done(state.identity.run_id, "explore", artifact_paths=[])
    explore_phase = new_state.phase("explore")
    # Artifacts from envelope must be used, not the empty artifact_paths=[]
    assert "explore.artifact.json" in explore_phase.artifact_paths


def test_mark_done_falls_back_to_artifact_paths_when_no_file(tmp_path):
    """When no phase-result file exists, artifact_paths param is used, no exception."""
    conductor = OcNewConductor(tmp_path)
    state = conductor.start("test fallback")
    run_dir = tmp_path / ".opencontext" / "runs" / state.identity.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "explore.artifact.json").write_text("{}", encoding="utf-8")

    # No phase-result.explore.json created — should fall back to artifact_paths
    new_state = conductor.mark_done(
        state.identity.run_id, "explore", artifact_paths=["explore.artifact.json"]
    )
    explore_phase = new_state.phase("explore")
    assert "explore.artifact.json" in explore_phase.artifact_paths
