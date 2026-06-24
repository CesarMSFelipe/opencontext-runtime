"""Tests for ContextBudgetBroker (slice 4: context economy)."""

from __future__ import annotations

from opencontext_core.context.broker import ContextBudgetBroker


def test_allocate_records_and_returns_remaining() -> None:
    broker = ContextBudgetBroker(total_budget=10_000)
    remaining = broker.allocate("design", 4_000)
    assert remaining == 6_000
    assert broker.remaining() == 6_000
    assert broker.total_allocated() == 4_000


def test_allocate_multiple_phases_accumulates() -> None:
    broker = ContextBudgetBroker(total_budget=10_000)
    broker.allocate("design", 4_000)
    remaining = broker.allocate("apply", 3_000)
    assert remaining == 3_000
    assert broker.allocations() == {"design": 4_000, "apply": 3_000}


def test_allocate_never_returns_negative() -> None:
    broker = ContextBudgetBroker(total_budget=1_000)
    remaining = broker.allocate("design", 1_500)
    assert remaining == 0
    assert broker.over_budget() is True