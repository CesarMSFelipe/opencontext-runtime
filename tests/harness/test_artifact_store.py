"""PR-002 ART-02: file-backed ArtifactStore CRUD + checksum verification."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.artifact_store import ArtifactStore
from opencontext_core.harness.sessions import ensure_layout
from opencontext_core.models.artifact import ArtifactWriteRequest


def test_write_then_get_roundtrips(tmp_path: Path) -> None:
    run_dir = ensure_layout(tmp_path, "sess_1", "run_1")
    store = ArtifactStore(run_dir)
    ref = store.write(
        ArtifactWriteRequest(
            run_id="run_1",
            session_id="sess_1",
            kind="patch",
            content="a diff",
            media_type="text/x-diff",
        )
    )
    got = store.get(ref.artifact_id)
    assert got.kind == "patch"
    assert got.path == ref.path
    assert got.checksum == ref.checksum
    assert got.checksum  # non-empty


def test_verify_checksum_detects_corruption(tmp_path: Path) -> None:
    run_dir = ensure_layout(tmp_path, "sess_1", "run_1")
    store = ArtifactStore(run_dir)
    ref = store.write(
        ArtifactWriteRequest(
            run_id="run_1",
            session_id="sess_1",
            kind="spec",
            content="original",
            media_type="text/plain",
        )
    )
    assert store.verify_checksum(ref.artifact_id) is True
    (run_dir / ref.path).write_text("tampered", encoding="utf-8")
    assert store.verify_checksum(ref.artifact_id) is False


def test_list_for_run_isolates_runs(tmp_path: Path) -> None:
    rd1 = ensure_layout(tmp_path, "sess_1", "run_a")
    rd2 = ensure_layout(tmp_path, "sess_1", "run_b")
    ArtifactStore(rd1).write(
        ArtifactWriteRequest(run_id="run_a", session_id="sess_1", kind="spec", content="a")
    )
    ArtifactStore(rd2).write(
        ArtifactWriteRequest(run_id="run_b", session_id="sess_1", kind="spec", content="b")
    )
    refs = ArtifactStore(rd1).list_for_run("run_a")
    assert len(refs) == 1
    assert refs[0].run_id == "run_a"


def test_source_classification_persisted(tmp_path: Path) -> None:
    run_dir = ensure_layout(tmp_path, "sess_1", "run_1")
    store = ArtifactStore(run_dir)
    ref = store.write(
        ArtifactWriteRequest(
            run_id="run_1", session_id="sess_1", kind="spec", content="x", source="user-provided"
        )
    )
    assert store.get(ref.artifact_id).source == "user-provided"
