"""PR-012 Phase 4.3 / CONV — the ProviderGateway facade.

Policy is enforced BEFORE any adapter dispatch (a secret-bearing request is
blocked pre-dispatch); structured-output is validated; the provider response
cache reuses identical calls; and the air-gapped degradation still produces a
local answer rather than crashing.
"""

from __future__ import annotations

import pytest

from opencontext_core.cache.provider_cache import ProviderResponseCache
from opencontext_core.cache.store import CcrBackedCacheStore
from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.errors import StructuredOutputError
from opencontext_core.models.context import ContextItem, ContextPriority, DataClassification
from opencontext_core.models.llm import LLMRequest, LLMResponse
from opencontext_core.providers.gateway import ProviderGateway
from opencontext_core.safety.firewall import ContextFirewall, FirewallBlockedError


class _CountingGateway:
    """Base gateway that records how many times it was actually dispatched."""

    def __init__(self, content: str = "ok") -> None:
        self.calls = 0
        self._content = content

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            content=self._content,
            provider=request.provider,
            model=request.model,
            input_tokens=3,
            output_tokens=2,
        )


def _config() -> OpenContextConfig:
    return OpenContextConfig.model_validate(default_config_data())


def _req(*, items: list[ContextItem] | None = None, metadata: dict | None = None) -> LLMRequest:
    return LLMRequest(
        prompt="hello",
        provider="mock",
        model="mock-llm",
        max_output_tokens=128,
        context_items=items or [],
        metadata=metadata or {},
    )


def _secret_item() -> ContextItem:
    return ContextItem(
        id="leak",
        content='aws = "AKIAIOSFODNN7EXAMPLE"\nsk = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"',
        source="src/leak.py",
        source_type="file",
        priority=ContextPriority.P1,
        tokens=20,
        score=0.5,
        classification=DataClassification.INTERNAL,
    )


def test_policy_is_enforced_before_dispatch() -> None:
    base = _CountingGateway()
    gw = ProviderGateway(base, firewall=ContextFirewall(_config()))
    with pytest.raises(FirewallBlockedError) as exc:
        gw.generate(_req(items=[_secret_item()]))
    assert "raw_secret_detected_before_provider_call" in str(exc.value)
    assert base.calls == 0  # blocked BEFORE any adapter dispatch


def test_allowed_local_call_passes_through_the_facade() -> None:
    base = _CountingGateway(content="answer")
    gw = ProviderGateway(base, firewall=ContextFirewall(_config()))
    resp = gw.generate(_req())
    assert resp.content == "answer"
    assert base.calls == 1


def test_structured_output_validation_rejects_malformed_response() -> None:
    base = _CountingGateway(content='{"unexpected": 1}')
    gw = ProviderGateway(base)
    schema = {"type": "object", "required": ["answer"]}
    with pytest.raises(StructuredOutputError):
        gw.generate(_req(metadata={"response_schema": schema}))


def test_structured_output_validation_accepts_conforming_response() -> None:
    base = _CountingGateway(content='{"answer": "yes"}')
    gw = ProviderGateway(base)
    schema = {"type": "object", "required": ["answer"]}
    resp = gw.generate(_req(metadata={"response_schema": schema}))
    assert resp.content == '{"answer": "yes"}'


def test_identical_call_hits_the_provider_cache_with_no_provider_call() -> None:
    base = _CountingGateway(content="cached-answer")
    cache = ProviderResponseCache(CcrBackedCacheStore(), enabled=True)
    gw = ProviderGateway(base, cache=cache)
    first = gw.generate(_req())
    second = gw.generate(_req())
    assert first.content == "cached-answer"
    assert second.content == "cached-answer"
    assert second.metadata.get("cache_hit") is True
    assert base.calls == 1  # the second identical call was served from cache
