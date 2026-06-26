"""REQ-01b: conductor.mark_done for archive phase calls OcNewArchiveGate fail-closed."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.oc_new.archive_gate import OcNewArchiveGate
from opencontext_core.oc_new.conductor import OcNewConductor
from opencontext_core.oc_new.models import OcNewRunState
from opencontext_core.workflow.phase_result import PhaseResultEnvelope


def _write_envelope(
    run_dir: Path,
    run_id: str,
    change_id: str,
    phase_name: str,
    artifacts: list[str] | None = None,
    status: str = "passed",
) -> None:
    envelope = PhaseResultEnvelope(
        run_id=run_id,
        change_id=change_id,
        phase=phase_name,
        status=status,
        duration_s=0.0,
        artifacts=artifacts or [],
    )
    (run_dir / f"phase-result.{phase_name}.json").write_text(
        envelope.model_dump_json(), encoding="utf-8"
    )


def _write_all_gate_files(run_dir: Path, *, include_harness: bool = True) -> None:
    """Write all OcNewArchiveGate.REQUIRED files into run_dir."""
    content_map = {
        "verify-report.json": '{"verdict": "PASS"}',
        "compliance-matrix.json": '{"passed": true}',
        "harness-report.json": '{"passed": true, "failures": []}',
    }
    for name in OcNewArchiveGate.REQUIRED:
        if name == "harness-report.json" and not include_harness:
            continue
        (run_dir / name).write_text(content_map.get(name, "{}"), encoding="utf-8")


def _drive_to_archive(
    conductor: OcNewConductor, run_dir: Path, run_id: str, change_id: str
) -> OcNewRunState:
    """Drive an oc-new run up to (but not including) archive by marking all prior phases done."""

    # Phases in order before archive:
    phases_to_drive = [
        ("explore", ["explore.artifact.json"]),
        ("propose", ["proposal.md", "proposal.json", "propose.artifact.json"]),
        ("spec", ["spec.md", "spec.json", "spec.artifact.json"]),
        ("design", ["design.md", "design.json", "design.artifact.json"]),
        ("tasks", ["tasks.md", "tasks.json", "tasks.artifact.json"]),
    ]

    state = conductor.store.load(run_id)
    for phase_name, artifacts in phases_to_drive:
        for a in artifacts:
            (run_dir / a).write_text("{}", encoding="utf-8")
        _write_envelope(run_dir, run_id, change_id, phase_name, artifacts=artifacts)
        state = conductor.mark_done(run_id, phase_name)

    # approval phase — write approval.json
    (run_dir / "approval.json").write_text('{"status": "approved"}', encoding="utf-8")
    _write_envelope(run_dir, run_id, change_id, "approval", artifacts=["approval.json"])
    state = conductor.mark_done(run_id, "approval")

    # apply phase
    apply_artifacts = ["apply-manifest.json", "apply.artifact.json"]
    for a in apply_artifacts:
        (run_dir / a).write_text("{}", encoding="utf-8")
    _write_envelope(run_dir, run_id, change_id, "apply", artifacts=apply_artifacts)
    state = conductor.mark_done(run_id, "apply")

    # verify phase — write all verify expected artifacts
    verify_artifacts = [
        "verify-report.json",
        "verify.artifact.json",
        "compliance-matrix.json",
        "harness-report.json",
        "tdd-evidence.json",
        "quality-gate.json",
    ]
    verify_content = {
        "verify-report.json": '{"verdict": "PASS"}',
        "compliance-matrix.json": '{"passed": true}',
        "harness-report.json": '{"passed": true, "failures": []}',
    }
    for a in verify_artifacts:
        (run_dir / a).write_text(verify_content.get(a, "{}"), encoding="utf-8")
    _write_envelope(run_dir, run_id, change_id, "verify", artifacts=verify_artifacts)
    state = conductor.mark_done(run_id, "verify")

    # review phase
    review_artifacts = ["review-report.json", "review.artifact.json"]
    for a in review_artifacts:
        (run_dir / a).write_text("{}", encoding="utf-8")
    _write_envelope(run_dir, run_id, change_id, "review", artifacts=review_artifacts)
    state = conductor.mark_done(run_id, "review")

    return state


def test_archive_blocked_when_harness_report_missing(tmp_path: Path) -> None:
    """Forged run with missing harness-report.json → archive blocked."""
    conductor = OcNewConductor(tmp_path)
    state = conductor.start("Archive gate test missing harness")

    run_dir = tmp_path / ".opencontext" / "runs" / state.identity.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    state = _drive_to_archive(
        conductor, run_dir, state.identity.run_id, state.identity.change_id
    )

    # Remove harness-report.json to simulate a failed harness.
    harness_path = run_dir / "harness-report.json"
    if harness_path.exists():
        harness_path.unlink()

    # Write archive envelope claiming passed status.
    _write_envelope(
        run_dir, state.identity.run_id, state.identity.change_id, "archive",
        artifacts=["archive-report.json"],
    )

    state = conductor.mark_done(state.identity.run_id, "archive")

    archive_phase = state.phase("archive")  # type: ignore[arg-type]
    assert archive_phase.status == "blocked", (
        f"Expected blocked, got {archive_phase.status!r}. "
        f"Warnings: {archive_phase.warnings}"
    )
    warnings = archive_phase.warnings or []
    assert any("harness-report.json" in w for w in warnings), (
        f"Expected warning mentioning harness-report.json, got: {warnings}"
    )
