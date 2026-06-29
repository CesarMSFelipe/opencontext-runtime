"""PR-012 Phase 4.2 — named routing strategies (book §25).

``local_first`` / ``cheapest`` prefer a local backend; ``highest_quality`` never
downgrades to local; ``balanced`` reproduces the legacy budget-first route
byte-for-byte.
"""

from __future__ import annotations

from opencontext_core.operating_model.call_budget import CallBudgetManager
from opencontext_core.operating_model.performance import ModelRoleRouter, RoutingStrategy


def _router(strategy: RoutingStrategy) -> ModelRoleRouter:
    return ModelRoleRouter(
        roles={"generate": {"provider": "openai", "model": "gpt-4o"}},
        budget_manager=CallBudgetManager(),
        local_providers=["ollama", "lmstudio", "localai", "mock"],
        strategy=strategy,
    )


def test_local_first_prefers_a_local_provider() -> None:
    route = _router(RoutingStrategy.LOCAL_FIRST).route_with_budget("generate")
    assert route["provider"] in {"ollama", "lmstudio", "localai", "mock"}


def test_cheapest_prefers_a_local_provider() -> None:
    route = _router(RoutingStrategy.CHEAPEST).route_with_budget("generate")
    assert route["provider"] in {"ollama", "lmstudio", "localai", "mock"}


def test_highest_quality_keeps_the_preferred_paid_provider() -> None:
    route = _router(RoutingStrategy.HIGHEST_QUALITY).route_with_budget("generate")
    assert route == {"provider": "openai", "model": "gpt-4o"}


def test_balanced_reproduces_legacy_budget_first_route() -> None:
    # A router with no strategy argument (legacy default) and one with explicit
    # BALANCED must produce the identical route for the same inputs.
    roles = {"generate": {"provider": "openai", "model": "gpt-4o"}}
    legacy = ModelRoleRouter(roles=roles, budget_manager=CallBudgetManager())
    balanced = ModelRoleRouter(
        roles=roles, budget_manager=CallBudgetManager(), strategy=RoutingStrategy.BALANCED
    )
    assert balanced.route_with_budget("generate") == legacy.route_with_budget("generate")


def test_strategy_accepts_string_value() -> None:
    router = ModelRoleRouter(
        roles={"generate": {"provider": "openai", "model": "gpt-4o"}},
        budget_manager=CallBudgetManager(),
        strategy="local_first",
    )
    assert router.strategy is RoutingStrategy.LOCAL_FIRST
