"""Provider gateway v2 — PR-012 routing, fallback, redaction, adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ProviderCapability:
    name: str
    models: list[str]
    supports_streaming: bool = False
    supports_structured: bool = False
    max_tokens: int = 128000


class ProviderGateway:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderCapability] = {}

    def register(self, name: str, cap: ProviderCapability) -> None:
        self._providers[name] = cap

    def capabilities(self) -> list[ProviderCapability]:
        return list(self._providers.values())

    def best_for(self, min_tokens: int = 0) -> ProviderCapability | None:
        return max(
            (c for c in self._providers.values() if c.max_tokens >= min_tokens),
            key=lambda c: c.max_tokens,
            default=None,
        )


class FallbackRouter:
    def __init__(self, gateway: ProviderGateway) -> None:
        self._gw = gateway

    def route(self, preferred: str, fallback_order: list[str] | None = None) -> str:
        if preferred in self._gw._providers:
            return preferred
        for fb in fallback_order or []:
            if fb in self._gw._providers:
                return fb
        caps = self._gw.capabilities()
        return caps[0].name if caps else "unknown"


class StructuredOutputAdapter:
    def adapt(self, response: dict[str, Any], schema: dict[Any, Any]) -> dict[str, Any]:
        return {k: response.get(k) for k in schema if k in response}
