"""Marketplace — PR-016 package + trust + registry + benchmark-on-install."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MarketPackage:
    name: str
    version: str
    trust_score: float = 0.5


class MarketRegistry:
    def __init__(self) -> None:
        self._packages: dict[str, MarketPackage] = {}

    def register(self, pkg: MarketPackage) -> None:
        self._packages[pkg.name] = pkg

    def search(self, query: str) -> list[MarketPackage]:
        return [p for p in self._packages.values() if query.lower() in p.name.lower()]
