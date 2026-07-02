"""Tests for receipt CLI — verifies receipt list/show reads harness run artifacts.

T1 of product-polish-r14: harness writes .opencontext/runs/<run_id>/receipts/
receipts.jsonl (schema opencontext.phase_receipt.v1) but the old CLI read from
.opencontext/receipts/receipts.jsonl (flat RunReceiptStore). These tests assert
the CLI is wired to the actual writer location.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from opencontext_cli.commands.receipt_cmd import handle_receipt


def _write_phase_receipt(
    root: Path, run_id: str, receipt_id: str, phase: str = "apply"
) -> Path:
    """Write a minimal PhaseReceipt fixture under .opencontext/runs/<run_id>/receipts/."""
    receipts_dir = root / ".opencontext" / "runs" / run_id / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = receipts_dir / "receipts.jsonl"
    receipt = {
        "schema_version": "opencontext.phase_receipt.v1",
        "receipt_id": receipt_id,
        "run_id": run_id,
        "session_id": "",
        "workflow_id": None,
        "phase": phase,
        "status": "passed",
        "artifact_refs": [],
        "gate_digest": {},
        "required_harnesses": [],
        "decision_refs": [],
        "trace_id": None,
        "created_at": "2026-07-02T00:00:00+00:00",
    }
    with jsonl_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(receipt) + "\n")
    return jsonl_path


def test_receipt_list_finds_harness_phase_receipt(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """receipt list must show receipts from .opencontext/runs/*/receipts/receipts.jsonl."""
    _write_phase_receipt(tmp_path, "run-t1-001", "rcpt-t1-001")

    handle_receipt(SimpleNamespace(receipt_action="list", root=tmp_path, json=True))

    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    # At least one receipt must be listed; receipt_id must appear in data
    assert len(data) >= 1, f"Expected at least 1 receipt, got {len(data)}"
    ids = [str(item) for item in data]
    assert any("rcpt-t1-001" in i for i in ids), (
        f"Expected receipt_id 'rcpt-t1-001' in list output, got: {data}"
    )


def test_receipt_list_empty_when_no_runs(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """receipt list returns empty list when no run receipts exist."""
    handle_receipt(SimpleNamespace(receipt_action="list", root=tmp_path, json=True))

    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data == [], f"Expected empty list, got: {data}"


def test_receipt_show_by_receipt_id(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """receipt show <receipt_id> must return the harness receipt JSON."""
    _write_phase_receipt(tmp_path, "run-t1-002", "rcpt-t1-002", phase="spec")

    handle_receipt(
        SimpleNamespace(receipt_action="show", run_id="rcpt-t1-002", root=tmp_path, json=True)
    )

    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["receipt_id"] == "rcpt-t1-002"
    assert data["run_id"] == "run-t1-002"
    assert data["phase"] == "spec"
    assert data["status"] == "passed"


def test_receipt_show_by_run_id(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """receipt show <run_id> also resolves when the arg matches a run_id."""
    _write_phase_receipt(tmp_path, "run-t1-003", "rcpt-t1-003")

    handle_receipt(
        SimpleNamespace(receipt_action="show", run_id="run-t1-003", root=tmp_path, json=True)
    )

    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["run_id"] == "run-t1-003"


def test_receipt_show_not_found_exits_1(tmp_path: Path) -> None:
    """receipt show missing-id exits with code 1."""
    with pytest.raises(SystemExit) as exc_info:
        handle_receipt(
            SimpleNamespace(
                receipt_action="show", run_id="nonexistent-id", root=tmp_path, json=False
            )
        )
    assert exc_info.value.code == 1
