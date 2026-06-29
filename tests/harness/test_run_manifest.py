"""PR-002 MAN-01: RunManifest indexes a run's evidence and parses to schema."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.artifact_store import ArtifactStore
from opencontext_core.harness.receipt_store import ReceiptStore
from opencontext_core.harness.sessions import build_run_manifest, ensure_layout
from opencontext_core.models.artifact import ArtifactWriteRequest, Checkpoint
from opencontext_core.models.receipt import Receipt
from opencontext_core.models.run_manifest import RunManifest


def test_manifest_indexes_produced_evidence(tmp_path: Path) -> None:
    run_dir = ensure_layout(tmp_path, "sess_1", "run_1")

    ArtifactStore(run_dir).write(
        ArtifactWriteRequest(run_id="run_1", session_id="sess_1", kind="spec", content="hi")
    )
    ReceiptStore(run_dir).write(Receipt(run_id="run_1", kind="mutation", action="applied"))
    cp = Checkpoint(
        checkpoint_id="cp_1",
        session_id="sess_1",
        run_id="run_1",
        files=["x.py"],
        checksums={"x.py": "deadbeef"},
        snapshot_paths={},
        created_at="2026-01-01T00:00:00+00:00",
    )
    (run_dir / "checkpoints" / "cp_1.json").write_text(cp.model_dump_json(), encoding="utf-8")

    manifest = build_run_manifest(
        run_dir,
        session_id="sess_1",
        run_id="run_1",
        workflow_id="sdd",
        status="passed",
        events_path="events.jsonl",
    )

    assert len(manifest.artifacts) == 1
    assert len(manifest.receipts) == 1
    assert len(manifest.checkpoints) == 1
    assert manifest.checkpoints[0].checkpoint_id == "cp_1"
    assert manifest.events_path == "events.jsonl"


def test_manifest_validates_against_schema(tmp_path: Path) -> None:
    run_dir = ensure_layout(tmp_path, "sess_1", "run_1")
    manifest = build_run_manifest(run_dir, session_id="sess_1", run_id="run_1")
    # Round-trips through the v1 schema without error.
    reparsed = RunManifest.model_validate_json(manifest.model_dump_json())
    assert reparsed.schema_version == "opencontext.run_manifest.v1"
    assert reparsed.run_id == "run_1"
