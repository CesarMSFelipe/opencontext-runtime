"""Tests for BudgetLedger and PhaseBudget — spec §Domain 3."""

from __future__ import annotations

import pytest
import pydantic

from opencontext_core.agentic.budget import BudgetLedger, PhaseBudget


def test_phase_spend_accumulates() -> None:
    ledger = BudgetLedger(mode="strict", total_budget=2000)
    p1 = PhaseBudget(phase="explore", used_input_tokens=300, used_output_tokens=100)
    p2 = PhaseBudget(phase="spec", used_input_tokens=200, used_output_tokens=50)
    ledger = ledger.add_phase(p1).add_phase(p2)
    assert ledger.total_spent == 650
    assert ledger.used_total == 650


def test_over_budget_false_when_within_limit() -> None:
    ledger = BudgetLedger(mode="strict", total_budget=1000)
    ledger = ledger.add_phase(PhaseBudget(
        phase="explore", used_input_tokens=600, used_output_tokens=200
    ))
    assert ledger.total_spent == 800
    assert not ledger.over_budget


def test_over_budget_true_when_exceeded() -> None:
    ledger = BudgetLedger(mode="strict", total_budget=500)
    ledger = ledger.add_phase(PhaseBudget(
        phase="apply", used_input_tokens=400, used_output_tokens=250
    ))
    assert ledger.total_spent == 650
    assert ledger.over_budget


def test_no_total_budget_never_over() -> None:
    ledger = BudgetLedger(mode="warn", total_budget=None)
    ledger = ledger.add_phase(PhaseBudget(phase="archive", used_input_tokens=99999))
    assert not ledger.over_budget


def test_add_phase_is_immutable() -> None:
    original = BudgetLedger(mode="strict", total_budget=1000)
    updated = original.add_phase(PhaseBudget(phase="explore", used_input_tokens=100))
    assert len(original.phases) == 0
    assert len(updated.phases) == 1


def test_unknown_field_rejected() -> None:
    with pytest.raises(pydantic.ValidationError):
        BudgetLedger(mode="strict", bad_field="oops")  # type: ignore[call-arg]


def test_phase_budget_unknown_field_rejected() -> None:
    with pytest.raises(pydantic.ValidationError):
        PhaseBudget(phase="spec", not_a_field=42)  # type: ignore[call-arg]


def test_schema_version_default() -> None:
    ledger = BudgetLedger(mode="warn")
    assert ledger.schema_version == "opencontext.budget_ledger.v1"
