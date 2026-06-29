"""PR-002 RES-02: ResumeManager validates integrity + rehydrates, failing safely."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.harness.artifact_store import ArtifactStore
from opencontext_core.harness.resume import ResumeIntegrityError, ResumeManager
from opencontext_core.harness.sessions import build_run_manifest, ensure_layout, write_run_manifest
from opencontext_core.models.artifact import ArtifactWriteRequest
from opencontext_core.models.run_manifest import ArtifactRef


def _seed(tmp_path: Path, *, required: bool) -> tuple[Path, ArtifactRef]:
    run_dir = ensure_layout(tmp_path, "sess_1", "run_1")
    ref = ArtifactStore(run_dir).write(
        ArtifactWriteRequest(
            run_id="run_1",
            session_id="sess_1",
            kind="spec",
            content="payload",
            media_type="text/plain",
            required=required,
        )
    )
    write_run_manifest(run_dir, build_run_manifest(run_dir, session_id="sess_1", run_id="run_1"))
    return run_dir, ref


def test_missing_required_artifact_aborts(tmp_path: Path) -> None:
    run_dir, ref = _seed(tmp_path, required=True)
    (run_dir / ref.path).unlink()
    with pytest.raises(ResumeIntegrityError):
        ResumeManager(run_dir).validate()


def test_checksum_mismatch_aborts(tmp_path: Path) -> None:
    run_dir, ref = _seed(tmp_path, required=True)
    (run_dir / ref.path).write_text("tampered", encoding="utf-8")
    with pytest.raises(ResumeIntegrityError):
        ResumeManager(run_dir).validate()


def test_clean_manifest_rehydrates_refs(tmp_path: Path) -> None:
    run_dir, ref = _seed(tmp_path, required=True)
    result = ResumeManager(run_dir).validate()
    assert any(r.artifact_id == ref.artifact_id for r in result.rehydrated)


def test_non_required_missing_warns_not_aborts(tmp_path: Path) -> None:
    run_dir, ref = _seed(tmp_path, required=False)
    (run_dir / ref.path).unlink()
    result = ResumeManager(run_dir).validate()
    assert all(r.artifact_id != ref.artifact_id for r in result.rehydrated)
    assert any("missing" in w for w in result.warnings)


def test_missing_manifest_is_typed_error(tmp_path: Path) -> None:
    run_dir = ensure_layout(tmp_path, "sess_1", "run_1")
    with pytest.raises(ResumeIntegrityError):
        ResumeManager(run_dir).load_manifest()
