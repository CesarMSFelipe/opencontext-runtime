"""Tests for provider adapters."""

from __future__ import annotations

import pytest

from opencontext_core.providers.adapters import (
    MockAdapter,
    ProviderConfig,
    ProviderRegistry,
)


class TestMockAdapter:
    """Test mock adapter."""

    def test_is_available(self) -> None:
        adapter = MockAdapter(ProviderConfig(name="mock"))
        assert adapter.is_available()

    def test_chat(self) -> None:
        adapter = MockAdapter(ProviderConfig(name="mock"))
        response = adapter.chat([{"role": "user", "content": "Hello"}])
        assert response.content == "Mock response for testing"
        assert response.provider == "mock"
        assert response.model == "mock-llm"

    def test_list_models(self) -> None:
        adapter = MockAdapter(ProviderConfig(name="mock"))
        models = adapter.list_models()
        assert models == ["mock-llm"]


class TestProviderRegistry:
    """Test provider registry."""

    def test_list_providers(self) -> None:
        registry = ProviderRegistry()
        providers = registry.list_providers()
        assert len(providers) > 0
        names = [p["name"] for p in providers]
        assert "mock" in names

    def test_create_mock(self) -> None:
        registry = ProviderRegistry()
        adapter = registry.create("mock")
        assert adapter.is_available()

    def test_create_unknown(self) -> None:
        registry = ProviderRegistry()
        with pytest.raises(Exception):
            registry.create("unknown")

    def test_get_available(self) -> None:
        registry = ProviderRegistry()
        available = registry.get_available()
        assert "mock" in available
