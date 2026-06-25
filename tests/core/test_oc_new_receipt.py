"""Tests for write_receipt."""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.oc_new.models import ChangeIdentity, OcNewRunState, PhaseState
from opencontext_core.oc_new.receipt import write_receipt


def _state(tmp_path: Path) -> OcNewRunState:
    identity = ChangeIdentity.from_task("add graph health command")
    phases = [
        PhaseState(name="explore", status="passed"),
        PhaseState(name="propose", status="passed"),
        PhaseState(name="spec", status="pending"),
    ]
    return OcNewRunState(identity=identity, task="add graph health command", phases=phases)


def test_write_receipt_creates_file(tmp_path: Path) -> None:
    state = _state(tmp_path)
    run_dir = tmp_path / ".opencontext" / "runs" / state.identity.run_id
    run_dir.mkdir(parents=True)

    path = write_receipt(state, run_dir)

    assert path.exists()
    data = json.loads(path.read_text())
    assert data["schema_version"] == "opencontext.oc_new_receipt.v1"
    assert data["run_id"] == state.identity.run_id
    assert data["change_id"] == state.identity.change_id
    assert data["task"] == "add graph health command"
    assert "archived_at" in data


def test_write_receipt_appends_to_ledger(tmp_path: Path) -> None:
    state = _state(tmp_path)
    run_dir = tmp_path / ".opencontext" / "runs" / state.identity.run_id
    run_dir.mkdir(parents=True)

    write_receipt(state, run_dir)
    write_receipt(state, run_dir)

    ledger = tmp_path / ".opencontext" / "receipts" / "receipts.jsonl"
    lines = ledger.read_text().strip().splitlines()
    assert len(lines) == 2  # two appends
    for line in lines:
        entry = json.loads(line)
        assert entry["run_id"] == state.identity.run_id


def test_write_receipt_completed_phases(tmp_path: Path) -> None:
    state = _state(tmp_path)
    run_dir = tmp_path / ".opencontext" / "runs" / state.identity.run_id
    run_dir.mkdir(parents=True)

    path = write_receipt(state, run_dir)
    data = json.loads(path.read_text())

    assert data["completed_phases"] == ["explore", "propose"]
