from __future__ import annotations

from opencontext_core.operating_model import (
    CallBudgetConfig,
    CallBudgetManager,
    CallUsage,
    FreeProviderRegistry,
    ProviderType,
)


def test_call_usage_tracks_consumption() -> None:
    usage = CallUsage(provider="openai", model="gpt-4", limit=5)
    assert usage.remaining == 5
    assert usage.exhausted is False

    usage.use()
    assert usage.remaining == 4
    usage.use(3)
    assert usage.remaining == 1

    usage.use()
    assert usage.exhausted is True


def test_call_usage_cannot_exceed_limit() -> None:
    usage = CallUsage(provider="openai", model="gpt-4", limit=3)
    usage.use(3)
    assert usage.exhausted is True
    assert usage.remaining == 0

    result = usage.use(1)
    assert result is False


def test_call_budget_manager_registers_and_checks() -> None:
    manager = CallBudgetManager()
    manager.register_usage("openai", "gpt-4", limit=10)

    available, remaining = manager.check_budget("openai", "gpt-4")
    assert available is True
    assert remaining == 10


def test_call_budget_manager_consumes_calls() -> None:
    manager = CallBudgetManager()
    manager.consume("openai", "gpt-4")
    _available, remaining = manager.check_budget("openai", "gpt-4")
    assert remaining == 199


def test_call_budget_selects_local_when_paid_exhausted() -> None:
    config = CallBudgetConfig(local_preference_threshold=5, strict_mode=False)
    manager = CallBudgetManager(config=config)

    for _ in range(200):
        manager.consume("openai", "gpt-4")

    provider, _model, reason = manager.select_provider("openai", "gpt-4")
    assert provider in ["ollama", "lmstudio", "localai"]
    assert "local" in reason.lower()


def test_call_budget_strict_mode_selects_local() -> None:
    config = CallBudgetConfig(strict_mode=True)
    manager = CallBudgetManager(config=config)

    for _ in range(200):
        manager.consume("openai", "gpt-4")

    provider, _model, reason = manager.select_provider("openai", "gpt-4")
    assert provider == "ollama"
    assert "local" in reason.lower()


def test_provider_type_detection() -> None:
    manager = CallBudgetManager()
    assert manager.get_provider_type("ollama") == ProviderType.LOCAL
    assert manager.get_provider_type("huggingface") == ProviderType.FREE
    assert manager.get_provider_type("openai") == ProviderType.PAID


def test_free_provider_registry() -> None:
    registry = FreeProviderRegistry()

    assert "ollama" in registry.available_providers()
    assert "lmstudio" in registry.available_providers()

    endpoint = registry.get_endpoint("ollama")
    assert endpoint is not None
    assert "localhost:11434" in endpoint["endpoint"]

    assert registry.should_delegate_to_local("summarize") is True
    assert registry.should_delegate_to_local("complex_reasoning") is False


def test_budget_status_returns_all_providers() -> None:
    manager = CallBudgetManager()
    manager.register_usage("openai", "gpt-4", limit=100)
    manager.register_usage("ollama", "phi3", limit=50)

    status = manager.budget_status()
    assert "openai/gpt-4" in status
    assert "ollama/phi3" in status
    assert status["openai/gpt-4"]["limit"] == 100
    assert status["ollama/phi3"]["type"] == "local"
