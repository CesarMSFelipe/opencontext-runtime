"""Static flow smoke test — drives conductor through all 10 phases using file stubs."""

from __future__ import annotations

from opencontext_core.oc_new.conductor import OcNewConductor
from opencontext_core.oc_new.flow import OC_NEW_FLOW


def _phase(name: str):
    return next(p for p in OC_NEW_FLOW if p.name == name)


def test_flow_phase_personas() -> None:
    assert _phase("spec").persona == "oc-requirements"
    assert _phase("tasks").persona == "oc-planner"
    assert _phase("verify").persona == "oc-harness-verifier"
    assert _phase("archive").persona == "oc-archivist"


def test_verify_phase_expected_artifacts_include_evidence() -> None:
    artifacts = _phase("verify").expected_artifacts
    assert "compliance-matrix.json" in artifacts
    assert "harness-report.json" in artifacts


# Artifacts that each phase needs from the previous phase
_PHASE_ARTIFACTS: dict[str, list[str]] = {
    "explore": ["explore.artifact.json", "context-pack.json"],
    "propose": ["proposal.md", "proposal.json", "propose.artifact.json"],
    "spec": ["spec.md", "spec.json", "spec.artifact.json"],
    "design": ["design.md", "design.json", "design.artifact.json"],
    "tasks": ["tasks.md", "tasks.json", "tasks.artifact.json"],
    "approval": ["approval.json"],
    "apply": ["apply-manifest.json", "apply.artifact.json"],
    "verify": ["verify-report.json", "verify.artifact.json"],
    "review": ["review-report.json", "review.artifact.json"],
    "archive": ["archive-report.json", "archive.artifact.json", "receipt.json"],
}


def test_full_10_phase_static_flow(tmp_path):
    conductor = OcNewConductor(tmp_path)
    state = conductor.start("Add graph health command")

    assert state.current_phase == "explore"

    run_dir = tmp_path / ".opencontext" / "runs" / state.identity.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    flow_phases = [p.name for p in OC_NEW_FLOW]

    for phase_name in flow_phases:
        assert state.current_phase == phase_name, (
            f"Expected {phase_name}, got {state.current_phase}"
        )

        # Create all artifacts this phase produces
        artifacts = _PHASE_ARTIFACTS.get(phase_name, [])
        for artifact in artifacts:
            (run_dir / artifact).write_text("{}", encoding="utf-8")

        state = conductor.mark_done(
            state.identity.run_id,
            phase_name,
            artifact_paths=artifacts,
        )

    # All phases done
    assert state.next_action is not None
    assert state.next_action.kind == "done"
    assert state.current_phase is None
