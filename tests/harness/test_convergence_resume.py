"""PR-002 AR-CONV: decision-log/program-plan kinds, source enum, resume rehydration."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from opencontext_core.harness.artifact_store import ArtifactStore
from opencontext_core.harness.resume import ResumeIntegrityError, ResumeManager
from opencontext_core.harness.sessions import build_run_manifest, ensure_layout, write_run_manifest
from opencontext_core.models.artifact import ArtifactWriteRequest
from opencontext_core.models.run_manifest import ArtifactRef


def _seed_with(tmp_path: Path, requests: list[ArtifactWriteRequest]) -> tuple[Path, list]:
    run_dir = ensure_layout(tmp_path, "sess_1", "run_1")
    store = ArtifactStore(run_dir)
    refs = [store.write(r) for r in requests]
    write_run_manifest(run_dir, build_run_manifest(run_dir, session_id="sess_1", run_id="run_1"))
    return run_dir, refs


def test_decision_log_and_program_plan_kinds_writable(tmp_path: Path) -> None:
    run_dir = ensure_layout(tmp_path, "sess_1", "run_1")
    store = ArtifactStore(run_dir)
    dl = store.write(
        ArtifactWriteRequest(
            run_id="run_1",
            session_id="sess_1",
            kind="decision-log",
            content='{"a":1}\n',
            media_type="application/json",
        )
    )
    pp = store.write(
        ArtifactWriteRequest(
            run_id="run_1",
            session_id="sess_1",
            kind="program-plan",
            content="{}",
            media_type="application/json",
        )
    )
    assert store.verify_checksum(dl.artifact_id)
    assert store.verify_checksum(pp.artifact_id)
    kinds = {r.kind for r in store.list_for_run("run_1")}
    assert {"decision-log", "program-plan"} <= kinds


def test_invalid_artifact_source_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        ArtifactRef(artifact_id="art_1", run_id="r", kind="spec", path="p", source="invented")


def test_missing_decision_log_warns_and_resumes(tmp_path: Path) -> None:
    run_dir, _ = _seed_with(
        tmp_path,
        [ArtifactWriteRequest(run_id="run_1", session_id="sess_1", kind="spec", content="x")],
    )
    result = ResumeManager(run_dir).validate()
    assert any("decision-log" in w for w in result.warnings)


def test_decision_context_rehydrated(tmp_path: Path) -> None:
    dl_content = '{"decision":{"run_id":"run_1"}}\n{"decision":{"run_id":"run_1"}}\n'
    run_dir, _ = _seed_with(
        tmp_path,
        [
            ArtifactWriteRequest(
                run_id="run_1",
                session_id="sess_1",
                kind="decision-log",
                content=dl_content,
                media_type="application/json",
            )
        ],
    )
    result = ResumeManager(run_dir).validate()
    assert len(result.decision_log_entries) == 2


def test_profile_snapshot_present_validates_clean(tmp_path: Path) -> None:
    run_dir, _ = _seed_with(
        tmp_path,
        [
            ArtifactWriteRequest(
                run_id="run_1",
                session_id="sess_1",
                kind="confidence-report",
                content='{"profile":"balanced"}',
                media_type="application/json",
                metadata={"snapshot": "profile_capability"},
            )
        ],
    )
    result = ResumeManager(run_dir).validate()
    assert not any("profile/capability snapshot" in w for w in result.warnings)


def test_profile_snapshot_corrupt_aborts(tmp_path: Path) -> None:
    run_dir, refs = _seed_with(
        tmp_path,
        [
            ArtifactWriteRequest(
                run_id="run_1",
                session_id="sess_1",
                kind="confidence-report",
                content='{"profile":"balanced"}',
                media_type="application/json",
                metadata={"snapshot": "profile_capability"},
            )
        ],
    )
    (run_dir / refs[0].path).write_text("BROKEN", encoding="utf-8")
    with pytest.raises(ResumeIntegrityError):
        ResumeManager(run_dir).validate()


def test_profile_snapshot_absent_warns(tmp_path: Path) -> None:
    run_dir, _ = _seed_with(
        tmp_path,
        [ArtifactWriteRequest(run_id="run_1", session_id="sess_1", kind="spec", content="x")],
    )
    result = ResumeManager(run_dir).validate()
    assert any("profile/capability snapshot" in w for w in result.warnings)
