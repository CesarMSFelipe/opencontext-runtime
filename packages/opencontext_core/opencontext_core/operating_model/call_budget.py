"""Call budget management for LLM providers with local fallback support."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC


class ProviderType(Enum):
    """Provider category for routing decisions."""

    LOCAL = "local"
    FREE = "free"
    PAID = "paid"
    FREE_TIER = "free_tier"

    def __str__(self) -> str:
        return self.value


@dataclass
class CallUsage:
    """Track usage for a specific provider/model combination."""

    provider: str
    model: str
    limit: int = field(default=200)
    used: int = field(default=0)
    window_start: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit

    def use(self, count: int = 1) -> bool:
        """Consume calls if available. Returns True if successful."""
        if self.exhausted:
            return False
        self.used = min(self.limit, self.used + count)
        return True

    def reset_if_needed(self, window_hours: int = 24) -> None:
        """Reset usage if window has expired."""
        elapsed = (datetime.now(tz=UTC) - self.window_start).total_seconds() / 3600
        if elapsed >= window_hours:
            self.used = 0
            self.window_start = datetime.now(tz=UTC)


class CallBudgetConfig(BaseModel):
    """Configuration for call budget management."""

    model_config = ConfigDict(extra="forbid")

    default_limit: int = Field(default=200, description="Default call limit per provider")
    window_hours: int = Field(default=24, description="Reset window in hours")
    local_preference_threshold: int = Field(
        default=50, description="Switch to local when remaining calls drop below this"
    )
    strict_mode: bool = Field(
        default=True, description="Block calls when budget exhausted instead of falling back"
    )


class CallBudgetManager:
    """Manages call budgets across providers to minimize paid API usage."""

    FREE_PROVIDERS: ClassVar[dict[str, ProviderType]] = {
        "ollama": ProviderType.LOCAL,
        "lmstudio": ProviderType.LOCAL,
        "localai": ProviderType.LOCAL,
        "llamacpp": ProviderType.LOCAL,
        "gpt4all": ProviderType.LOCAL,
        "huggingface": ProviderType.FREE,
        "huggingface-inference": ProviderType.FREE,
        "cohere-free": ProviderType.FREE_TIER,
        "anthropic-free-tier": ProviderType.FREE_TIER,
        "openai-free-tier": ProviderType.FREE_TIER,
    }

    def __init__(self, config: CallBudgetConfig | None = None) -> None:
        self.config = config or CallBudgetConfig()
        self._usage: dict[tuple[str, str], CallUsage] = defaultdict(
            lambda: CallUsage(provider="", model="", limit=self.config.default_limit)
        )

    def register_usage(self, provider: str, model: str, limit: int | None = None) -> None:
        """Register a provider/model combination with optional limit."""
        key = (provider, model)
        if key not in self._usage:
            self._usage[key] = CallUsage(
                provider=provider,
                model=model,
                limit=limit or self.config.default_limit,
            )
        self._usage[key].reset_if_needed(self.config.window_hours)

    def check_budget(self, provider: str, model: str) -> tuple[bool, int]:
        """Check if calls are available. Returns (available, remaining)."""
        key = (provider, model)
        if key not in self._usage:
            self.register_usage(provider, model)
        usage = self._usage[key]
        usage.reset_if_needed(self.config.window_hours)
        return (not usage.exhausted, usage.remaining)

    def consume(self, provider: str, model: str, count: int = 1) -> bool:
        """Consume calls. Returns True if successful."""
        key = (provider, model)
        if key not in self._usage:
            self.register_usage(provider, model)
        usage = self._usage[key]
        usage.reset_if_needed(self.config.window_hours)
        if usage.exhausted:
            return False
        return usage.use(count)

    def get_provider_type(self, provider: str) -> ProviderType:
        """Determine provider category."""
        provider_lower = provider.lower()
        if provider_lower in self.FREE_PROVIDERS:
            return self.FREE_PROVIDERS[provider_lower]
        return ProviderType.PAID

    def select_provider(
        self,
        preferred_provider: str,
        model: str,
        local_providers: list[str] | None = None,
    ) -> tuple[str, str, str]:
        """
        Select the best provider based on budget and preference.
        Returns (provider, model, reason).
        """
        if local_providers is None:
            local_providers = ["ollama", "lmstudio", "localai"]

        available, remaining = self.check_budget(preferred_provider, model)

        if available:
            if remaining < self.config.local_preference_threshold:
                for local in local_providers:
                    local_available, _ = self.check_budget(local, model)
                    if local_available:
                        return (local, model, "budget_low_switching_to_local")
                return (preferred_provider, model, "budget_low_using_paid")
            return (preferred_provider, model, "budget_ok")

        if not available and self.config.strict_mode:
            for local in local_providers:
                local_key = (local, model)
                if local_key not in self._usage or not self._usage[local_key].exhausted:
                    return (local, model, "paid_exhausted_using_local")
            return (preferred_provider, model, "no_fallback_available")

        for local in local_providers:
            return (local, model, "paid_unavailable_using_local")

        return (preferred_provider, model, "fallback_failed")

    def budget_status(self) -> dict[str, dict[str, Any]]:
        """Return current budget status for all registered providers."""
        status = {}
        now = datetime.now(tz=UTC)

        for (provider, model), usage in self._usage.items():
            elapsed = (now - usage.window_start).total_seconds() / 3600
            status[f"{provider}/{model}"] = {
                "provider": provider,
                "model": model,
                "used": usage.used,
                "limit": usage.limit,
                "remaining": usage.remaining,
                "exhausted": usage.exhausted,
                "window_hours_remaining": max(0, self.config.window_hours - elapsed),
                "type": self.get_provider_type(provider).value,
            }

        return status


class FreeProviderRegistry:
    """Registry of free/opensource LLM providers for fallback."""

    FREE_ENDPOINTS: ClassVar[dict[str, dict[str, Any]]] = {
        "huggingface": {
            "endpoint": "https://api-inference.huggingface.co/models",
            "models": ["microsoft/Phi-3-mini-4k-instruct", "mistralai/Mixtral-8x7B-Instruct-v0.1"],
        },
        "ollama": {"endpoint": "http://localhost:11434", "models": ["phi3", "gemma", "llama3"]},
        "lmstudio": {"endpoint": "http://localhost:1234/v1", "models": ["local-model"]},
        "cohere": {"endpoint": "https://api.cohere.ai/v1", "requires_key": True},
    }

    def __init__(self) -> None:
        self._working: dict[str, bool] = {}

    def get_endpoint(self, provider: str) -> dict[str, Any] | None:
        """Get endpoint configuration for a free provider."""
        return self.FREE_ENDPOINTS.get(provider)

    def mark_working(self, provider: str, working: bool = True) -> None:
        """Mark a provider as working or not."""
        self._working[provider] = working

    def is_working(self, provider: str) -> bool:
        """Check if a provider is marked as working."""
        return self._working.get(provider, True)  # Assume working by default

    def available_providers(self, only_working: bool = True) -> list[str]:
        """Return list of available free providers."""
        if only_working:
            return [p for p in self.FREE_ENDPOINTS.keys() if self.is_working(p)]
        return list(self.FREE_ENDPOINTS.keys())

    def should_delegate_to_local(self, task_complexity: str) -> bool:
        """Determine if a task should use local model based on complexity."""
        simple_tasks = {"summarize", "format", "classify", "extract", "translate"}
        return task_complexity.lower() in simple_tasks
