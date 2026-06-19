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


class ProviderGateway:
    """Adapts a ``ProviderAdapter.chat`` to ``LLMGateway.generate``."""

    def __init__(self, adapter: ProviderAdapter, *, provider: str, model: str) -> None:
        self._adapter = adapter
        self._provider = provider
        self._model = model

    def generate(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self._model
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})
        # The adapter raises ProviderError if its API key is missing — that
        # surfaces as a phase failure/warning rather than producing a fake answer.
        resp = self._adapter.chat(
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
    adapter_cls = _ADAPTERS.get(provider)
    if adapter_cls is None:
        return None
    api_key = os.environ.get(_KEY_ENV.get(provider, ""), "").strip() or None
    config = ProviderConfig(name=provider, api_key=api_key, max_tokens=4000)
    return ProviderGateway(adapter_cls(config), provider=provider, model=model)
