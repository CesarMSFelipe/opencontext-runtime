"""Tests for the provider->LLMGateway bridge.

Behavior, real round-trip (via the in-process MockAdapter), and the graceful
no-key failure path — not just "it builds".
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.errors import ConfigurationError, ProviderError
from opencontext_core.llm.provider_gateway import ProviderGateway, build_provider_gateway
from opencontext_core.models.llm import LLMRequest
from opencontext_core.runtime import OpenContextRuntime


def _req(provider: str = "mock", model: str = "mock-llm") -> LLMRequest:
    return LLMRequest(prompt="hello world", provider=provider, model=model, max_output_tokens=128)


def test_known_providers_build_unknown_returns_none() -> None:
    for provider in ("anthropic", "openai", "openrouter", "ollama", "mock"):
        assert isinstance(build_provider_gateway(provider, "m"), ProviderGateway)
    assert build_provider_gateway("does-not-exist", "m") is None


def test_generate_round_trips_through_mock_adapter() -> None:
    gateway = build_provider_gateway("mock", "mock-llm")
    assert gateway is not None
    resp = gateway.generate(_req())
    assert resp.provider == "mock"
    assert resp.content == "Mock response for testing"  # pin the adapter's real output
    assert resp.output_tokens == 5


def test_real_provider_without_key_builds_but_fails_at_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Construction must NOT require a key (so building a runtime never crashes)...
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    gateway = build_provider_gateway("anthropic", "claude-x")
    assert gateway is not None
    # ...but calling it without a key fails loudly rather than faking an answer.
    with pytest.raises(ProviderError):
        gateway.generate(_req("anthropic", "claude-x"))


def test_runtime_with_real_provider_builds_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: _gateway_from_config used to raise for every non-mock provider,
    # so a runtime with a real provider configured could not even be constructed.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    data = default_config_data()
    data["models"]["default"]["provider"] = "anthropic"
    data["models"]["default"]["model"] = "claude-sonnet-4-6"
    tmp = Path(tempfile.mkdtemp())
    (tmp / "opencontext.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")

    runtime = OpenContextRuntime(
        config_path=str(tmp / "opencontext.yaml"), storage_path=tmp / ".storage"
    )
    assert runtime.llm_gateway is not None  # built, not raised


def test_air_gapped_forbids_external_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    data = default_config_data()
    data["models"]["default"]["provider"] = "anthropic"
    data["security"]["mode"] = "air_gapped"
    data["security"]["external_providers_enabled"] = False
    config = OpenContextConfig.model_validate(data)
    runtime = OpenContextRuntime.__new__(OpenContextRuntime)  # bypass __init__ wiring
    runtime.config = config
    with pytest.raises(ConfigurationError):
        runtime._gateway_from_config()
