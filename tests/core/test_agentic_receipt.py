"""Tests for AgenticReceipt — spec §Domain 7."""

from __future__ import annotations

import pytest
import pydantic

from opencontext_core.agentic.receipt import AgenticReceipt


def _minimal_receipt(**kwargs: object) -> AgenticReceipt:
    defaults: dict[str, object] = {
        "run_id": "ocnew-abc",
        "change_id": "add-health",
        "flow_mode": "automatic",
        "openspec_mode": "off",
        "budget_mode": "warn",
        "git_mode": "none",
        "status": "done",
        "completed_phases": ["explore"],
    }
    defaults.update(kwargs)
    return AgenticReceipt(**defaults)  # type: ignore[arg-type]


def test_serialises_without_budget_data() -> None:
    receipt = _minimal_receipt()
    dumped = receipt.model_dump()
    assert "run_id" in dumped
    assert dumped["budget_summary"] is None
    assert dumped["status"] == "done"


def test_v1_fields_present_in_minimal_receipt() -> None:
    receipt = _minimal_receipt()
    dumped = receipt.model_dump()
    for field in ("run_id", "change_id", "flow_mode", "status", "completed_phases"):
        assert field in dumped, f"Missing field: {field}"


def test_serialises_with_all_extended_fields() -> None:
    receipt = _minimal_receipt(
        budget_summary="800/1000 tokens",
        kg_snapshot_hash="kg-abc123",
        memory_snapshot_hash="mem-def456",
        context_substrate_summary="12 files packed",
        git_work_plan_hash="git-xyz",
    )
    dumped = receipt.model_dump()
    assert dumped["budget_summary"] == "800/1000 tokens"
    assert dumped["kg_snapshot_hash"] == "kg-abc123"
    assert dumped["memory_snapshot_hash"] == "mem-def456"
    assert dumped["context_substrate_summary"] == "12 files packed"


def test_unknown_field_rejected() -> None:
    with pytest.raises(pydantic.ValidationError):
        _minimal_receipt(not_a_field="oops")  # type: ignore[misc]


def test_json_round_trip() -> None:
    receipt = _minimal_receipt(completed_phases=["explore", "spec", "apply"])
    json_str = receipt.model_dump_json()
    restored = AgenticReceipt.model_validate_json(json_str)
    assert restored.completed_phases == ["explore", "spec", "apply"]


def test_schema_version_default() -> None:
    receipt = _minimal_receipt()
    assert receipt.schema_version == "opencontext.agentic_receipt.v1"
