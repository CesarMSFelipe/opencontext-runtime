"""Tests for G4 — conductor approval.json content validation (AC-G4-1, AC-G4-2, AC-G4-3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.oc_new.conductor import OcNewConductor
from opencontext_core.oc_new.flow import OC_NEW_FLOW
from opencontext_core.oc_new.models import OcNewRunState, PhaseState


def _write_approval(run_dir: Path, content: bytes | str) -> None:
    approval_path = run_dir / "approval.json"
    approval_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        approval_path.write_bytes(content)
    else:
        approval_path.write_text(content)


# ---------------------------------------------------------------------------
# Unit tests for _validate_approval_content
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload,expect_blocked",
    [
        # AC-G4-1: status != "approved" → blocked
        ({"status": "pending"}, True),
        # AC-G4-1: empty object (no keys) → blocked
        ({}, True),
        # AC-G4-1: approved=False → blocked
        ({"approved": False}, True),
        # AC-G4-2: approved=True (bool) → unblocked
        ({"approved": True}, False),
        # status == "approved" → unblocked
        ({"status": "approved"}, False),
    ],
)
def test_validate_approval_content_json_payloads(
    tmp_path: Path, payload: dict, expect_blocked: bool
) -> None:
    conductor = OcNewConductor(root=tmp_path)
    run_dir = tmp_path / ".opencontext" / "runs" / "test-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_approval(run_dir, json.dumps(payload))

    result = conductor._validate_approval_content(run_dir)

    if expect_blocked:
        assert result is not None, f"Expected block reason for payload {payload!r}, got None"
        assert isinstance(result, str)
    else:
        assert result is None, f"Expected None (no block) for payload {payload!r}, got {result!r}"


def test_validate_approval_content_malformed_json(tmp_path: Path) -> None:
    """AC-G4-3: malformed JSON → blocked, no exception raised."""
    conductor = OcNewConductor(root=tmp_path)
    run_dir = tmp_path / ".opencontext" / "runs" / "test-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_approval(run_dir, b"not-valid-json{{{")

    result = conductor._validate_approval_content(run_dir)

    assert result is not None
    assert "not valid JSON" in result


def test_validate_approval_content_missing_file(tmp_path: Path) -> None:
    """Missing approval.json → fail-closed block reason returned."""
    conductor = OcNewConductor(root=tmp_path)
    run_dir = tmp_path / ".opencontext" / "runs" / "test-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    # Do NOT write approval.json

    result = conductor._validate_approval_content(run_dir)

    assert result is not None
    assert "not found" in result


# ---------------------------------------------------------------------------
# Integration test: _advance() blocks on bad approval.json (AC-G5-3 companion)
# ---------------------------------------------------------------------------


def _make_pre_apply_state(tmp_path: Path) -> tuple[OcNewConductor, OcNewRunState]:
    """Build a conductor + state where all phases before 'apply' are passed."""
    conductor = OcNewConductor(root=tmp_path)
    # Pre-populate phases: all phases before 'apply' marked passed; apply onward pending.
    pre_apply = {"explore", "propose", "spec", "design", "tasks", "approval"}
    phases = [
        PhaseState(name=p.name, status="passed" if p.name in pre_apply else "pending")
        for p in OC_NEW_FLOW
    ]

    from opencontext_core.oc_new.models import ChangeIdentity, OcNewRunState

    identity = ChangeIdentity.from_task("integration-approval-test")
    state = OcNewRunState(identity=identity, task="integration-approval-test", phases=phases)

    # Put required artifacts for 'apply' into run_dir so _missing_artifacts passes.
    run_dir = tmp_path / ".opencontext" / "runs" / identity.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    for artifact in ["approval.json", "tasks.md"]:
        (run_dir / artifact).write_text("{}")

    return conductor, state, identity.run_id


def test_advance_blocks_on_pending_approval(tmp_path: Path) -> None:
    """End-to-end: _advance() returns kind='blocked' when approval.json has status=pending."""
    conductor, state, run_id = _make_pre_apply_state(tmp_path)

    run_dir = tmp_path / ".opencontext" / "runs" / run_id
    _write_approval(run_dir, json.dumps({"status": "pending"}))

    result = conductor._advance(state)

    assert result.next_action is not None
    assert result.next_action.kind == "blocked"
    assert result.next_action.phase == "apply"
