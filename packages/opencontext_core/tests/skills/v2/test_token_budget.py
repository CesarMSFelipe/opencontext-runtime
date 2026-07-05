"""Tests for skills.v2.token_budget — budget tracking with exceeded sentinel."""

from __future__ import annotations

from opencontext_core.skills.v2.token_budget import (
    BUDGET_EXCEEDED,
    TokenBudget,
)


def test_exceeded_returns_budget_exceeded() -> None:
    """Spending beyond the cap returns BUDGET_EXCEEDED; the request is rejected."""
    b = TokenBudget(cap=100, used=0)
    assert b.try_spend(60).accepted
    assert b.used == 60
    # second spend would exceed → rejected with sentinel
    outcome = b.try_spend(50)
    assert not outcome.accepted
    assert outcome.reason == BUDGET_EXCEEDED
    # used is unchanged on rejection
    assert b.used == 60
