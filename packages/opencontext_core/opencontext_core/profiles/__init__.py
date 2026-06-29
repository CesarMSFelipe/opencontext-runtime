"""Execution Profiles & Strategies layer (PR-000.2, L3 Governance).

Named ``ExecutionProfile``s bind token budget, retry/diagnosis attempts, harness
strictness, and provider routing into one unit; ``ExecutionProfileStrategy``s map
intents (``fast``/``cheap``/...) onto profiles; ``ExecutionProfileResolver``
resolves a profile/strategy against the live ``CapabilityGraph`` into a snapshot
decision input.

Distinct from the per-phase *model* profile (``sdd_model_profile``) and install
setup presets (``setup/presets.py``). The built-in profile catalog lives in
``capabilities.registry`` (imported there to keep the id vocabulary in one place).
"""

from __future__ import annotations

from opencontext_core.profiles.definition import (
    EXECUTION_PROFILE_SCHEMA_VERSION,
    EXECUTION_STRATEGY_SCHEMA_VERSION,
    ExecutionProfile,
    ExecutionProfileStrategy,
    HarnessStrictness,
    ProviderRouting,
)
from opencontext_core.profiles.resolver import (
    ExecutionProfileResolver,
    ResolvedProfile,
)
from opencontext_core.profiles.strategy import (
    BUILTIN_STRATEGIES,
    builtin_strategy_ids,
    get_strategy,
)

__all__ = [
    "BUILTIN_STRATEGIES",
    "EXECUTION_PROFILE_SCHEMA_VERSION",
    "EXECUTION_STRATEGY_SCHEMA_VERSION",
    "ExecutionProfile",
    "ExecutionProfileResolver",
    "ExecutionProfileStrategy",
    "HarnessStrictness",
    "ProviderRouting",
    "ResolvedProfile",
    "builtin_strategy_ids",
    "get_strategy",
]
