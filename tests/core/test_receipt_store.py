"""Tests for RunReceiptStore."""

from __future__ import annotations

import json

import pytest

from opencontext_core.operating_model.receipts import RunReceiptStore
from opencontext_core.operating_model.team import RunReceipt, RunReceiptGenerator


def _make_receipt(run_id: str = "run-001") -> RunReceipt:
    return RunReceiptGenerator().generate(
        workflow_id="wf-1",
        policy="{}",
        context_pack="ctx",
        prompt="fix bug",
        provider="openai",
        model="gpt-4",
        trace_id="t1",
        input_tokens=10,
        output_tokens=5,
    )


def test_store_creates_receipts_dir(tmp_path):
    RunReceiptStore(tmp_path)
    assert (tmp_path / ".opencontext" / "receipts").exists()


def test_save_and_load_round_trip(tmp_path):
    store = RunReceiptStore(tmp_path)
    receipt = _make_receipt()
    store.save(receipt)
    loaded = store.load(receipt.run_id)
    assert loaded.run_id == receipt.run_id
    assert loaded.provider == receipt.provider
    assert loaded.schema_version == "opencontext.run_receipt.v2"


def test_list_insertion_order(tmp_path):
    store = RunReceiptStore(tmp_path)
    ids = []
    for _ in range(3):
        r = _make_receipt()
        store.save(r)
        ids.append(r.run_id)
    listed = [r.run_id for r in store.list()]
    assert listed == ids


def test_load_missing_raises(tmp_path):
    store = RunReceiptStore(tmp_path)
    with pytest.raises(FileNotFoundError):
        store.load("nonexistent")


def test_verify_valid_receipt(tmp_path):
    store = RunReceiptStore(tmp_path)
    r = _make_receipt()
    store.save(r)
    result = store.verify(r.run_id)
    assert result["ok"] is True


def test_verify_corrupt_line_returns_false(tmp_path):
    store = RunReceiptStore(tmp_path)
    r = _make_receipt()
    store.save(r)
    store_file = tmp_path / ".opencontext" / "receipts" / "receipts.jsonl"
    with store_file.open("a") as fh:
        fh.write('{"run_id": "corrupt-run", INVALID JSON\n')
    result = store.verify("corrupt-run")
    assert result["ok"] is False


def test_verify_missing_returns_not_found(tmp_path):
    store = RunReceiptStore(tmp_path)
    result = store.verify("ghost-run")
    assert result["ok"] is False
    assert result["error"] == "not_found"


def test_no_raw_prompt_in_stored_jsonl(tmp_path):
    store = RunReceiptStore(tmp_path)
    r = _make_receipt()
    store.save(r)
    store_file = tmp_path / ".opencontext" / "receipts" / "receipts.jsonl"
    raw = store_file.read_text()
    data = json.loads(raw.strip())
    assert "prompt_hash" in data
    assert data.get("prompt_hash") != "fix bug"
