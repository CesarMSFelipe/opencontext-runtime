"""PR-002 RBK-02: rollback emits RollbackReceipt + report artifact + events."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.artifact_store import ArtifactStore
from opencontext_core.harness.checkpoint import CheckpointManager
from opencontext_core.harness.receipt_store import ReceiptStore
from opencontext_core.harness.rollback import rollback
from opencontext_core.harness.sessions import ensure_layout


def test_rollback_produces_full_evidence(tmp_path: Path) -> None:
    target = tmp_path / "f.py"
    target.write_text("ORIG\n", encoding="utf-8")
    run_dir = ensure_layout(tmp_path, "sess_1", "run_1")

    checkpoint = CheckpointManager(tmp_path).create([target], session_id="sess_1", run_id="run_1")
    assert checkpoint is not None
    # Simulate a mutation that must be rolled back.
    target.write_text("CHANGED\n", encoding="utf-8")

    artifact_store = ArtifactStore(run_dir)
    receipt_store = ReceiptStore(run_dir)
    events: list = []

    receipt = rollback(
        checkpoint,
        run_dir=run_dir,
        reason="post-apply gate failed",
        session_id="sess_1",
        run_id="run_1",
        artifact_store=artifact_store,
        receipt_store=receipt_store,
        events=events,
    )

    # Files restored.
    assert target.read_text(encoding="utf-8") == "ORIG\n"

    # RollbackReceipt persisted + linked to checkpoint.
    assert receipt.checkpoint_id == checkpoint.id
    assert receipt_store.list_rollback_receipts()[0].receipt_id == receipt.receipt_id

    # Rollback-report artifact written and retrievable.
    assert receipt.report_artifact_id is not None
    report_ref = artifact_store.get(receipt.report_artifact_id)
    assert report_ref.kind == "rollback-report"

    # Both lifecycle events appended in order.
    assert [e.action for e in events] == ["rollback.started", "rollback.completed"]
    assert events[0].metadata["family"] == "runtime"
