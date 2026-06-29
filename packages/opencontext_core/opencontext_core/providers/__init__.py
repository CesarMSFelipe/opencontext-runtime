"""Provider layer: adapters, capability model, and cost model (book §25, L7).

The unified ``ProviderGateway`` facade lives in
``opencontext_core.providers.gateway`` and is imported by full path (it pulls the
routing/policy/receipt stack); the lightweight capability and cost surfaces are
re-exported here for convenience.
"""

from opencontext_core.providers.capabilities import (
    ProviderCapability,
    capabilities_for,
    providers_with,
    supports,
)
from opencontext_core.providers.cost_model import estimate_cost, pricing_for

__all__ = [
    "ProviderCapability",
    "capabilities_for",
    "estimate_cost",
    "pricing_for",
    "providers_with",
    "supports",
]
