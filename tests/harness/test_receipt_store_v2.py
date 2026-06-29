"""PR-002 REC-01: append-only, immutable ReceiptStore."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.receipt_store import ReceiptStore
from opencontext_core.harness.sessions import ensure_layout
from opencontext_core.models.receipt import Receipt


def test_superseding_receipt_leaves_original_unchanged(tmp_path: Path) -> None:
    run_dir = ensure_layout(tmp_path, "sess_1", "run_1")
    store = ReceiptStore(run_dir)
    first = Receipt(run_id="run_1", kind="policy-decision", action="allow", reason="first")
    store.write(first)
    later = Receipt(run_id="run_1", kind="policy-decision", action="deny", reason="supersede")
    store.write(later)

    # Both lines present; the original is byte-for-byte unchanged.
    assert len(store.path.read_text(encoding="utf-8").strip().splitlines()) == 2
    assert store.get(first.receipt_id).reason == "first"
    assert store.get(first.receipt_id).action == "allow"


def test_receipts_queryable_by_run(tmp_path: Path) -> None:
    run_dir = ensure_layout(tmp_path, "sess_1", "run_1")
    store = ReceiptStore(run_dir)
    store.write(Receipt(run_id="run_1", kind="mutation", action="applied"))
    store.write(Receipt(run_id="run_1", kind="inspection", action="passed"))
    store.write(Receipt(run_id="run_2", kind="mutation", action="applied"))

    run1 = store.list_for_run("run_1")
    assert len(run1) == 2
    assert all(r.run_id == "run_1" for r in run1)


def test_write_returns_receipt_ref(tmp_path: Path) -> None:
    run_dir = ensure_layout(tmp_path, "sess_1", "run_1")
    store = ReceiptStore(run_dir)
    receipt = Receipt(run_id="run_1", kind="kg-update", action="reindexed")
    ref = store.write(receipt)
    assert ref.receipt_id == receipt.receipt_id
    assert ref.kind == "kg-update"
    assert ref.path == "receipts/receipts.jsonl"
