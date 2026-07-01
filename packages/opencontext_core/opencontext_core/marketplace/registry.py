"""Marketplace — PR-016 package, trust, registry, benchmark-on-install."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MarketPackage:
    name: str
    version: str
    trust_score: float = 0.5
    install_count: int = 0
    benchmark_score: float | None = None


class MarketRegistry:
    def __init__(self) -> None:
        self._packages: dict[str, MarketPackage] = {}

    def register(self, pkg: MarketPackage) -> None:
        self._packages[pkg.name] = pkg

    def search(self, query: str) -> list[MarketPackage]:
        return [p for p in self._packages.values() if query.lower() in p.name.lower()]

    def benchmark_on_install(self, name: str, score: float) -> None:
        if name in self._packages:
            self._packages[name].benchmark_score = score
            self._packages[name].install_count += 1


OFFICIAL_PACKS: list[str] = ["bench-tool", "studio-theme-default", "provider-mock"]
