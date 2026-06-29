"""Bridge a chat-style ``ProviderAdapter`` to the ``LLMGateway`` protocol.

Without this, ``_gateway_from_config`` could only return the mock gateway and
raised for every real provider — so the agentic loop never had a real executor.
This adapts the existing Anthropic/OpenAI/OpenRouter/local adapters
(``providers/adapters.py``) to the provider-neutral ``generate(LLMRequest)``
interface the harness and runtime consume.
"""

from __future__ import annotations

import os

from opencontext_core.models.llm import LLMRequest, LLMResponse
from opencontext_core.providers.adapters import (
    AnthropicAdapter,
    LocalAdapter,
    MockAdapter,
    OpenAIAdapter,
    OpenRouterAdapter,
    ProviderAdapter,
    ProviderConfig,
)

# Provider key -> adapter class. Names match config ``models.default.provider``.
_ADAPTERS: dict[str, type[ProviderAdapter]] = {
    "anthropic": AnthropicAdapter,
    "openai": OpenAIAdapter,
    "openrouter": OpenRouterAdapter,
    "ollama": LocalAdapter,
    "local": LocalAdapter,
    "mock": MockAdapter,
}

# Provider key -> environment variable holding the API key.
_KEY_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def build_adapter(provider: str, *, max_tokens: int = 4000) -> ProviderAdapter | None:
    """Build a provider adapter, pulling its API key from the env.

    Returns ``None`` for an unknown provider. Construction never requires the key
    — a missing key only fails at call time. Shared by the legacy shim, the
    ``build_provider_gateway`` helper, and the PR-012 ``ProviderGateway`` facade
    (``providers/gateway.py``) so there is a single adapter-build path.
    """

    adapter_cls = _ADAPTERS.get(provider)
    if adapter_cls is None:
        return None
    api_key = os.environ.get(_KEY_ENV.get(provider, ""), "").strip() or None
    return adapter_cls(ProviderConfig(name=provider, api_key=api_key, max_tokens=max_tokens))


class ProviderGateway:
    """Adapts a ``ProviderAdapter.chat`` to ``LLMGateway.generate``."""

    def __init__(self, adapter: ProviderAdapter, *, provider: str, model: str) -> None:
        self._adapter = adapter
        self._provider = provider
        self._model = model

    def generate(self, request: LLMRequest) -> LLMResponse:
        adapter = self._adapter
        # Honor a routed provider (e.g. a budget swap to a local backend) instead of
        # always calling the construction-time adapter. Otherwise a swap to 'ollama'
        # would still hit the Anthropic/OpenAI adapter with model='llama3' and 404.
        # Budget swaps only ever target LOCAL providers, so this re-dispatch adds no
        # external egress the firewall did not already approve.
        if request.provider and request.provider != self._provider:
            routed = build_adapter(request.provider)
            if routed is not None:
                adapter = routed
        model = request.model or self._model
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})
        # The adapter raises ProviderError if its API key is missing — that
        # surfaces as a phase failure/warning rather than producing a fake answer.
        resp = adapter.chat(
            messages,
            model=model,
            max_tokens=request.max_output_tokens,
        )
        return LLMResponse(
            content=resp.content,
            provider=resp.provider or request.provider,
            model=resp.model or model,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            metadata=resp.metadata or {},
        )


def build_provider_gateway(provider: str, model: str) -> ProviderGateway | None:
    """Build a gateway for a known provider, pulling its API key from the env.

    Returns ``None`` for an unknown provider (caller decides how to fail).
    Construction never requires the key — a missing key only fails at call time —
    so building a runtime with a real provider configured does not crash.
    """
    adapter = build_adapter(provider)
    if adapter is None:
        return None
    return ProviderGateway(adapter, provider=provider, model=model)


# Name-collision resolution (compat/collisions.py — "ProviderGateway", rule
# ``namespace``): this module's ``ProviderGateway`` is the legacy per-provider
# adapter shim and is KEPT as-is for the ``runtime.gateway_enabled=False`` path.
# The PR-012 unified facade is a DISTINCT class in ``providers/gateway.py``,
# disambiguated by package. ``_AdapterDispatcher`` is the design-doc name for the
# adapter-dispatch role this shim plays inside the facade composition.
_AdapterDispatcher = ProviderGateway
