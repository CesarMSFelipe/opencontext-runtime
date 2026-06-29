"""PR-002 APR-01: ApplyPhase emits per-file ApplyReceipts with before/after checksums."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.models import BudgetMode
from opencontext_core.harness.phases import ApplyPhase
from opencontext_core.harness.receipt_store import ReceiptStore
from opencontext_core.harness.runner import HarnessRunner


def _run_apply(tmp_path: Path, edits: list[dict]) -> Path:
    runner = HarnessRunner(root=tmp_path)
    runner._durable_artifacts = True
    state = runner.create_run("sdd", "apply receipt test")
    state.apply_edits = edits
    cfg = runner.config.phases.get("apply")
    result = ApplyPhase(cfg, BudgetMode.OFF).run(state)
    return Path(result.metadata["durable_run_dir"])


def test_modified_file_records_distinct_before_after(tmp_path: Path) -> None:
    target = tmp_path / "f.py"
    target.write_text("OLD\n", encoding="utf-8")

    run_dir = _run_apply(tmp_path, [{"path": str(target), "content": "NEW\n"}])
    receipts = ReceiptStore(run_dir).list_apply_receipts()

    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.changed is True
    assert receipt.operation == "modify"
    assert receipt.checksum_before and receipt.checksum_after
    assert receipt.checksum_before != receipt.checksum_after
    assert receipt.diff_path and receipt.diff_path.startswith("patches/patch-")


def test_noop_write_records_unchanged(tmp_path: Path) -> None:
    target = tmp_path / "f.py"
    # newline="" writes LF byte-exact (no CRLF translation on Windows) so the
    # pre-existing file matches ApplyPhase's byte-exact write and the no-op is detected.
    target.write_text("SAME\n", encoding="utf-8", newline="")

    run_dir = _run_apply(tmp_path, [{"path": str(target), "content": "SAME\n"}])
    receipts = ReceiptStore(run_dir).list_apply_receipts()

    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.changed is False
    assert receipt.checksum_before == receipt.checksum_after


def test_created_file_has_no_before(tmp_path: Path) -> None:
    target = tmp_path / "new.py"  # absent before apply

    run_dir = _run_apply(tmp_path, [{"path": str(target), "content": "HELLO\n"}])
    receipts = ReceiptStore(run_dir).list_apply_receipts()

    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.operation == "create"
    assert receipt.changed is True
    assert receipt.checksum_before is None
    assert receipt.checksum_after
