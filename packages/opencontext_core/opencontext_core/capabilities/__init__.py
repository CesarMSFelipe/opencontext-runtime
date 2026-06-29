"""Environment Capability Graph layer (PR-000.2, L3 Governance).

A typed graph of what the local environment can do — test/lint/type tooling, LLM
provider, agent clients — with dependency edges and graceful-degradation helpers.
Built from live detection (``build_capability_graph``) and consumed by ``doctor``,
the execution-profile resolver, and capability-aware workflow selection.

Distinct from the client ``CapabilityMatrix`` (``configurator/capability.py``),
which models per-agent features.
"""

from __future__ import annotations

from opencontext_core.capabilities.constraints import (
    CapabilityConstraint,
    GateDegradation,
    plan_gate_degradation,
)
from opencontext_core.capabilities.detector import STRICT_HARNESS, build_capability_graph
from opencontext_core.capabilities.graph import (
    CapabilityGraph,
    CapabilityKind,
    CapabilityNode,
)
from opencontext_core.capabilities.registry import (
    BUILTIN_PROFILES,
    DEFAULT_PROFILE_ID,
    KNOWN_TOOLING_CAPABILITIES,
    builtin_profile_ids,
    get_profile,
)

__all__ = [
    "BUILTIN_PROFILES",
    "DEFAULT_PROFILE_ID",
    "KNOWN_TOOLING_CAPABILITIES",
    "STRICT_HARNESS",
    "CapabilityConstraint",
    "CapabilityGraph",
    "CapabilityKind",
    "CapabilityNode",
    "GateDegradation",
    "build_capability_graph",
    "builtin_profile_ids",
    "get_profile",
    "plan_gate_degradation",
]
