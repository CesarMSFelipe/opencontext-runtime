"""LLM Provider adapters for OpenContext.

Supports multiple providers through a unified interface:
- OpenRouter (unified API for 100+ models)
- Anthropic (Claude models)
- OpenAI (GPT models)
- Local models (via HTTP)
- Mock (default, for testing)

All adapters follow the same interface and respect provider policies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from opencontext_core.errors import ProviderError


@dataclass
class ModelResponse:
    """Standardized response from any provider."""

    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = "stop"
    metadata: dict[str, Any] | None = None


@dataclass
class ProviderConfig:
    """Configuration for a provider adapter."""

    name: str
    api_key: str | None = None
    base_url: str | None = None
    timeout: int = 60
    max_retries: int = 3
    temperature: float = 0.7
    max_tokens: int = 4000


class ProviderAdapter(ABC):
    """Abstract base class for LLM provider adapters."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> ModelResponse:
        """Send a chat completion request."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available (API key set, etc.)."""
        pass

    @abstractmethod
    def list_models(self) -> list[str]:
        """List available models."""
        pass


class MockAdapter(ProviderAdapter):
    """Mock adapter for testing without API keys."""

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> ModelResponse:
        return ModelResponse(
            content="Mock response for testing",
            model="mock-llm",
            provider="mock",
            input_tokens=10,
            output_tokens=5,
        )

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[str]:
        return ["mock-llm"]


class OpenRouterAdapter(ProviderAdapter):
    """Adapter for OpenRouter API (100+ models)."""

    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self.base_url = config.base_url or self.DEFAULT_BASE_URL
        self.api_key = config.api_key

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> ModelResponse:
        if not self.is_available():
            raise ProviderError("OpenRouter API key not set")

        model = kwargs.get("model", "openrouter/auto")
        try:
            import requests

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://opencontext.dev",
                    "X-Title": "OpenContext Runtime",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": kwargs.get("temperature", self.config.temperature),
                    "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                },
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            choice = data["choices"][0]
            usage = data.get("usage", {})

            return ModelResponse(
                content=choice["message"]["content"],
                model=data.get("model", model),
                provider="openrouter",
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                finish_reason=choice.get("finish_reason", "stop"),
                metadata={"raw_response": data},
            )
        except Exception as exc:
            raise ProviderError(f"OpenRouter request failed: {exc}") from exc

    def is_available(self) -> bool:
        return self.api_key is not None and len(self.api_key) > 0

    def list_models(self) -> list[str]:
        if not self.is_available():
            return []
        try:
            import requests

            response = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            return [m["id"] for m in data.get("data", [])]
        except Exception:
            return []


class AnthropicAdapter(ProviderAdapter):
    """Adapter for Anthropic Claude API."""

    DEFAULT_BASE_URL = "https://api.anthropic.com/v1"

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self.base_url = config.base_url or self.DEFAULT_BASE_URL
        self.api_key = config.api_key

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> ModelResponse:
        if not self.is_available():
            raise ProviderError("Anthropic API key not set")

        model = kwargs.get("model", "claude-sonnet-4-20250514")
        try:
            import requests

            response = requests.post(
                f"{self.base_url}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                    "temperature": kwargs.get("temperature", self.config.temperature),
                },
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            content = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content += block.get("text", "")

            usage = data.get("usage", {})
            return ModelResponse(
                content=content,
                model=data.get("model", model),
                provider="anthropic",
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                finish_reason=data.get("stop_reason", "stop"),
                metadata={"raw_response": data},
            )
        except Exception as exc:
            raise ProviderError(f"Anthropic request failed: {exc}") from exc

    def is_available(self) -> bool:
        return self.api_key is not None and len(self.api_key) > 0

    def list_models(self) -> list[str]:
        return [
            "claude-opus-4",
            "claude-sonnet-4-20250514",
            "claude-haiku-4-5",
        ]


class OpenAIAdapter(ProviderAdapter):
    """Adapter for OpenAI API."""

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self.base_url = config.base_url or self.DEFAULT_BASE_URL
        self.api_key = config.api_key

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> ModelResponse:
        if not self.is_available():
            raise ProviderError("OpenAI API key not set")

        model = kwargs.get("model", "gpt-4o")
        try:
            import requests

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": kwargs.get("temperature", self.config.temperature),
                    "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                },
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            choice = data["choices"][0]
            usage = data.get("usage", {})

            return ModelResponse(
                content=choice["message"]["content"],
                model=data.get("model", model),
                provider="openai",
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                finish_reason=choice.get("finish_reason", "stop"),
                metadata={"raw_response": data},
            )
        except Exception as exc:
            raise ProviderError(f"OpenAI request failed: {exc}") from exc

    def is_available(self) -> bool:
        return self.api_key is not None and len(self.api_key) > 0

    def list_models(self) -> list[str]:
        return ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini"]


class LocalAdapter(ProviderAdapter):
    """Adapter for local HTTP servers (Ollama, vLLM, etc.)."""

    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self.base_url = config.base_url or self.DEFAULT_BASE_URL

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> ModelResponse:
        model = kwargs.get("model", "llama3")
        try:
            import requests

            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": kwargs.get("temperature", self.config.temperature),
                    },
                },
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            data = response.json()

            return ModelResponse(
                content=data.get("message", {}).get("content", ""),
                model=model,
                provider="local",
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
                metadata={"raw_response": data},
            )
        except Exception as exc:
            raise ProviderError(f"Local server request failed: {exc}") from exc

    def is_available(self) -> bool:
        try:
            import requests

            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        try:
            import requests

            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []


class ProviderRegistry:
    """Registry of available provider adapters."""

    def __init__(self) -> None:
        self.adapters: dict[str, type[ProviderAdapter]] = {
            "mock": MockAdapter,
            "openrouter": OpenRouterAdapter,
            "anthropic": AnthropicAdapter,
            "openai": OpenAIAdapter,
            "local": LocalAdapter,
        }

    def create(
        self,
        provider: str,
        config: ProviderConfig | None = None,
    ) -> ProviderAdapter:
        """Create a provider adapter instance."""

        adapter_class = self.adapters.get(provider)
        if adapter_class is None:
            raise ProviderError(f"Unknown provider: {provider}")

        if config is None:
            config = ProviderConfig(name=provider)

        return adapter_class(config)

    def list_providers(self) -> list[dict[str, Any]]:
        """List all registered providers."""

        result = []
        for name, adapter_class in self.adapters.items():
            try:
                adapter = adapter_class(ProviderConfig(name=name))
                available = adapter.is_available()
                models = adapter.list_models() if available else []
                result.append(
                    {
                        "name": name,
                        "available": available,
                        "models": models,
                    }
                )
            except Exception:
                result.append(
                    {
                        "name": name,
                        "available": False,
                        "models": [],
                    }
                )
        return result

    def get_available(self) -> list[str]:
        """Get list of available providers."""

        return [p["name"] for p in self.list_providers() if p["available"]]


# Global registry instance
registry = ProviderRegistry()
