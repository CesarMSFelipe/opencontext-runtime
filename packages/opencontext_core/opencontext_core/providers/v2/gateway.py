"""Provider gateway v2 — PR-012 routing + fallback + redaction + adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderCapability:
    name: str
    models: list[str]
    supports_streaming: bool = False

class ProviderGateway:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderCapability] = {}

    def register(self, name: str, cap: ProviderCapability) -> None:
        self._providers[name] = cap

    def capabilities(self) -> list[ProviderCapability]:
        return list(self._providers.values())


class FallbackRouter:
    def __init__(self, gateway: ProviderGateway) -> None:
        self._gw = gateway

    def route(self, preferred: str) -> str:
        if preferred in self._gw._providers:
            return preferred
        caps = self._gw.capabilities()
        return caps[0].name if caps else "unknown"
