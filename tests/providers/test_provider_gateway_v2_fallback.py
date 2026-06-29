"""PR-012 Phase 4.4 / CONV — automatic fallback within retry_limit (book §25).

Fallback fires on timeout / quota / provider error / unsupported capability — not
only budget exhaustion. It is bounded by ``retry_limit``, preserves the
``LLMResponse`` contract, and raises ``provider_fallback_exhausted`` when no
fallback remains.
"""

from __future__ import annotations

import pytest

from opencontext_core.errors import ProviderError
from opencontext_core.models.llm import LLMRequest, LLMResponse
from opencontext_core.providers.adapters import ModelResponse
from opencontext_core.providers.capabilities import ProviderCapability
from opencontext_core.providers.gateway import ProviderGateway


class _FailingGateway:
    """Primary base gateway that always fails with a given error."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.calls = 0

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        raise self._exc


class _StubAdapter:
    """Fallback adapter returning a canned response (offline, deterministic)."""

    def __init__(self, provider: str) -> None:
        self._provider = provider

    def chat_with_retries(self, messages: list[dict[str, str]], **kwargs: object) -> ModelResponse:
        return ModelResponse(
            content="fallback-answer",
            model=str(kwargs.get("model", "m")),
            provider=self._provider,
            input_tokens=1,
            output_tokens=1,
        )


def _stub_factory(provider: str) -> _StubAdapter:
    return _StubAdapter(provider)


def _req(metadata: dict | None = None) -> LLMRequest:
    return LLMRequest(
        prompt="hi",
        provider="anthropic",
        model="claude-x",
        max_output_tokens=64,
        metadata=metadata or {},
    )


@pytest.mark.parametrize(
    "exc",
    [
        ProviderError("Anthropic request failed: boom"),
        ProviderError("quota exceeded"),
        TimeoutError("silent host"),
    ],
)
def test_fallback_on_error_timeout_quota(exc: Exception) -> None:
    base = _FailingGateway(exc)
    gw = ProviderGateway(
        base,
        adapter_factory=_stub_factory,
        fallback_providers=("mock",),
        retry_limit=2,
    )
    resp = gw.generate(_req())
    assert resp.content == "fallback-answer"  # contract preserved
    assert resp.provider == "mock"
    assert base.calls == 1  # primary tried once, then fell back to the adapter


def test_fallback_exhausts_and_raises_when_no_fallback_remains() -> None:
    base = _FailingGateway(ProviderError("down"))
    gw = ProviderGateway(
        base,
        adapter_factory=_stub_factory,
        fallback_providers=(),  # nothing to fall back to
        retry_limit=2,
    )
    with pytest.raises(ProviderError, match="provider_fallback_exhausted"):
        gw.generate(_req())


def test_fallback_disabled_reraises_original_error() -> None:
    base = _FailingGateway(ProviderError("boom"))
    gw = ProviderGateway(base, adapter_factory=_stub_factory, fallback=False)
    with pytest.raises(ProviderError):
        gw.generate(_req())
    assert base.calls == 1


def test_unsupported_capability_triggers_capability_aware_fallback() -> None:
    # Primary "anthropic" lacks EMBEDDINGS; the only capable fallback offered is
    # "ollama" (advertises EMBEDDINGS), so the gateway must route there.
    base = _FailingGateway(ProviderError("unused: capability check fails first"))
    gw = ProviderGateway(
        base,
        adapter_factory=_stub_factory,
        fallback_providers=("mock", "ollama"),
        retry_limit=2,
    )
    resp = gw.generate(_req(metadata={"required_capabilities": [ProviderCapability.EMBEDDINGS]}))
    assert resp.provider == "ollama"  # mock lacks EMBEDDINGS and is skipped
    assert base.calls == 0  # capability gap detected before the primary dispatch
