"""PR-012 Phase 4.1 / CONV.1 — provider capability model + capability routing.

Behavior, not "it builds": every concrete adapter advertises a real capability
set, the lookup table answers correctly, and capability-filtered routing actually
selects a provider that advertises the required capability.
"""

from __future__ import annotations

from opencontext_core.operating_model.call_budget import CallBudgetManager
from opencontext_core.operating_model.performance import ModelRoleRouter
from opencontext_core.providers.adapters import (
    AnthropicAdapter,
    LocalAdapter,
    MockAdapter,
    OpenAIAdapter,
    OpenRouterAdapter,
    ProviderConfig,
)
from opencontext_core.providers.capabilities import (
    ProviderCapability,
    capabilities_for,
    providers_with,
    supports,
)
from opencontext_core.providers.cost_model import estimate_cost, pricing_for


def test_every_adapter_advertises_a_capability_set() -> None:
    cases = [
        (AnthropicAdapter, "anthropic"),
        (OpenAIAdapter, "openai"),
        (OpenRouterAdapter, "openrouter"),
        (LocalAdapter, "local"),
        (MockAdapter, "mock"),
    ]
    for adapter_cls, name in cases:
        adapter = adapter_cls(ProviderConfig(name=name))
        caps = adapter.capabilities()
        assert isinstance(caps, frozenset)
        assert caps == capabilities_for(name)


def test_capabilities_for_known_and_unknown() -> None:
    assert ProviderCapability.VISION in capabilities_for("anthropic")
    assert ProviderCapability.EMBEDDINGS in capabilities_for("openai")
    assert capabilities_for("mock") == frozenset()
    # Unknown provider advertises nothing rather than raising.
    assert capabilities_for("does-not-exist") == frozenset()


def test_supports_and_providers_with() -> None:
    assert supports("anthropic", frozenset({ProviderCapability.VISION}))
    assert not supports("ollama", frozenset({ProviderCapability.VISION}))
    vision = providers_with(frozenset({ProviderCapability.VISION}))
    assert "anthropic" in vision and "openai" in vision
    assert "mock" not in vision and "ollama" not in vision


def test_capability_filtered_routing_picks_a_capable_provider() -> None:
    # The role prefers a vision-incapable provider (mock); requiring VISION must
    # re-route to a provider that advertises it.
    router = ModelRoleRouter(
        roles={"generate": {"provider": "mock", "model": "mock-llm"}},
        budget_manager=CallBudgetManager(),
        required=frozenset({ProviderCapability.VISION}),
    )
    route = router.route_with_budget("generate")
    assert ProviderCapability.VISION in capabilities_for(route["provider"])


def test_cost_model_prices_paid_and_free_providers() -> None:
    # Paid providers price above zero; local/host/unknown price at zero.
    assert estimate_cost("anthropic", 1_000_000, 1_000_000) > 0.0
    assert pricing_for("ollama") == pricing_for("local")
    assert estimate_cost("ollama", 10_000, 10_000) == 0.0
    assert estimate_cost("host", 10_000, 10_000) == 0.0
    assert estimate_cost("unknown", 10_000, 10_000) == 0.0
