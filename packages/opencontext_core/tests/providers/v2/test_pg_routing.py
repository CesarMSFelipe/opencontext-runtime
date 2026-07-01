"""REQ-pg-v2-001: capability-based routing + no-provider raises."""

from __future__ import annotations

import pytest

from opencontext_core.providers.v2.routing import (
    RoutingEngine,
    RoutingStrategy,
    NoProviderAvailable,
)
from opencontext_core.providers.v2.spec import (
    CapabilityModel,
    ProviderSpec,
)


def _spec(pid: str, *, ctx: int = 4096, cost_in: float = 0.01, lat: int = 100,
           qual: float = 0.5, vision: bool = False, local: bool = False) -> ProviderSpec:
    return ProviderSpec(
        provider_id=pid,
        display_name=pid,
        capabilities=CapabilityModel(vision=vision),
        cost_input_per_1k=cost_in,
        cost_output_per_1k=cost_in,
        max_context_tokens=ctx,
        avg_latency_ms=lat,
        quality_score=qual,
        local_only=local,
    )


def test_REQ_pg_v2_001_capability_based() -> None:
    engine = RoutingEngine([
        _spec("cheap", cost_in=0.001, lat=500, qual=0.3),
        _spec("fast", cost_in=0.01, lat=10, qual=0.5),
        _spec("vision-only", vision=True),
    ])
    chosen = engine.route(required_capabilities=("vision",), strategy=RoutingStrategy.cheapest)
    assert chosen.provider_id == "vision-only"


def test_REQ_pg_v2_001_no_provider_raises() -> None:
    engine = RoutingEngine([_spec("text-only")])
    with pytest.raises(NoProviderAvailable):
        engine.route(required_capabilities=("vision",), strategy=RoutingStrategy.cheapest)


def test_six_strategies_present() -> None:
    names = {s.name for s in RoutingStrategy}
    assert names == {"cheapest", "fastest", "balanced", "highest_quality",
                     "local_first", "enterprise"}