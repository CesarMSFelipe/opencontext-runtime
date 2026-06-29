"""ExecutionStrategy resolution tests (RB-006)."""

from __future__ import annotations

from opencontext_core.economy.strategy import EconomyStrategy
from opencontext_core.runtime.execution_strategy import ExecutionStrategy, resolve_strategy

_STRICTNESS_RANK = {"off": 0, "warn": 1, "strict": 2}


def test_enterprise_is_stricter_than_low_cost() -> None:
    enterprise = resolve_strategy("enterprise")
    low_cost = resolve_strategy("low-cost")
    assert isinstance(enterprise, ExecutionStrategy)

    # Harness strictness and retry budget are strictly tighter for enterprise.
    assert _STRICTNESS_RANK[enterprise.harness_strictness] > _STRICTNESS_RANK[
        low_cost.harness_strictness
    ]
    assert enterprise.retry_budget > low_cost.retry_budget
    assert enterprise.budget_mode == "strict"
    assert low_cost.budget_mode == "off"


def test_difference_is_recorded_in_notes() -> None:
    enterprise = resolve_strategy("enterprise")
    assert any("enterprise" in note for note in enterprise.notes)
    assert any("strict" in note for note in enterprise.notes)


def test_unknown_profile_defaults_and_records_the_fallback() -> None:
    strategy = resolve_strategy("does-not-exist")
    assert strategy.profile == "balanced"
    assert any("defaulted" in note for note in strategy.notes)


def test_economy_decision_is_folded_into_notes() -> None:
    economy = EconomyStrategy.decide("aggressive", "apply")
    strategy = resolve_strategy("balanced", economy=economy)
    assert any("economy" in note for note in strategy.notes)
    assert any(str(economy.max_handoff_tokens) in note for note in strategy.notes)
