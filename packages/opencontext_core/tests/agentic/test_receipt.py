"""Tests for G5 — AgenticReceipt extended fields (AC-G5-1, AC-G5-2)."""

from __future__ import annotations

from opencontext_core.agentic.receipt import AgenticReceipt


def _minimal_receipt(**extra) -> AgenticReceipt:
    return AgenticReceipt(
        run_id="ocnew-test-run",
        change_id="test-change",
        flow_mode="automatic",
        openspec_mode="off",
        budget_mode="warn",
        git_mode="none",
        status="complete",
        completed_phases=["explore"],
        **extra,
    )


def test_agentic_receipt_accepts_all_four_new_fields() -> None:
    """AC-G5-1: AgenticReceipt can be instantiated with all 4 new fields."""
    receipt = _minimal_receipt(
        trace_id="trace-abc123",
        task="add health check endpoint",
        memory_mode="local",
        preset="agentic-safe",
    )
    assert receipt.trace_id == "trace-abc123"
    assert receipt.task == "add health check endpoint"
    assert receipt.memory_mode == "local"
    assert receipt.preset == "agentic-safe"


def test_agentic_receipt_new_fields_default_to_none() -> None:
    """AC-G5-2: fields default to None; existing receipts remain valid."""
    receipt = _minimal_receipt()
    assert receipt.trace_id is None
    assert receipt.task is None
    assert receipt.memory_mode is None
    assert receipt.preset is None


def test_agentic_receipt_partial_fields() -> None:
    """AC-G5-2: partial specification of new fields is valid."""
    receipt = _minimal_receipt(trace_id="trace-xyz", memory_mode="engram")
    assert receipt.trace_id == "trace-xyz"
    assert receipt.memory_mode == "engram"
    assert receipt.task is None
    assert receipt.preset is None


def test_agentic_receipt_round_trips_with_new_fields() -> None:
    """New fields survive model_dump / model_validate round-trip."""
    receipt = _minimal_receipt(
        trace_id="trace-roundtrip",
        task="round-trip-task",
        memory_mode="hybrid",
        preset="full-opencontext",
    )
    dumped = receipt.model_dump()
    assert dumped["trace_id"] == "trace-roundtrip"
    assert dumped["task"] == "round-trip-task"
    assert dumped["memory_mode"] == "hybrid"
    assert dumped["preset"] == "full-opencontext"

    restored = AgenticReceipt.model_validate(dumped)
    assert restored.trace_id == "trace-roundtrip"
    assert restored.preset == "full-opencontext"
