"""PR-012 RoutingEngine — capability-based selection with 6 strategies."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from opencontext_core.providers.v2.spec import ProviderSpec


class NoProviderAvailable(Exception):
    """No registered provider satisfies the request."""


class RoutingStrategy(str, Enum):
    cheapest = "cheapest"
    fastest = "fastest"
    balanced = "balanced"
    highest_quality = "highest_quality"
    local_first = "local_first"
    enterprise = "enterprise"


@dataclass
class RoutingEngine:
    providers: list[ProviderSpec]

    def _eligible(self, required: tuple[str, ...]) -> list[ProviderSpec]:
        if not required:
            return list(self.providers)
        return [p for p in self.providers if all(p.capabilities.has(c) for c in required)]

    def route(
        self,
        required_capabilities: tuple[str, ...] = (),
        strategy: RoutingStrategy = RoutingStrategy.balanced,
    ) -> ProviderSpec:
        eligible = self._eligible(required_capabilities)
        if not eligible:
            raise NoProviderAvailable(
                f"no provider satisfies required capabilities {required_capabilities!r}"
            )
        if strategy == RoutingStrategy.cheapest:
            return min(eligible, key=lambda p: p.cost_input_per_1k + p.cost_output_per_1k)
        if strategy == RoutingStrategy.fastest:
            return min(eligible, key=lambda p: p.avg_latency_ms)
        if strategy == RoutingStrategy.highest_quality:
            return max(eligible, key=lambda p: p.quality_score)
        if strategy == RoutingStrategy.local_first:
            locals_ = [p for p in eligible if p.local_only]
            return min(locals_ or eligible, key=lambda p: p.avg_latency_ms)
        if strategy == RoutingStrategy.enterprise:
            return max(
                eligible,
                key=lambda p: (p.quality_score, p.max_context_tokens),
            )
        # balanced: blend cost, latency, quality.
        return min(
            eligible,
            key=lambda p: (
                (p.cost_input_per_1k + p.cost_output_per_1k) * 100
                + p.avg_latency_ms / 10
                - p.quality_score * 50
            ),
        )