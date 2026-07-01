"""PR-012 Provider Gateway v2 public surface."""

from __future__ import annotations

__capability__ = "providers.v2"

from opencontext_core.providers.v2.adapter import ProviderAdapter
from opencontext_core.providers.v2.fallback import (
    FallbackChain,
    FallbackReason,
    FallbackReceipt,
)
from opencontext_core.providers.v2.routing import (
    NoProviderAvailable,
    RoutingEngine,
    RoutingStrategy,
)
from opencontext_core.providers.v2.spec import (
    CAPABILITY_FLAGS,
    CapabilityModel,
    ProviderSpec,
)

__all__ = [
    "CAPABILITY_FLAGS",
    "CapabilityModel",
    "FallbackChain",
    "FallbackReason",
    "FallbackReceipt",
    "NoProviderAvailable",
    "ProviderAdapter",
    "ProviderSpec",
    "RoutingEngine",
    "RoutingStrategy",
]
