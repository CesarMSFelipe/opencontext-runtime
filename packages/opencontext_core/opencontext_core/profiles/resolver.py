"""Resolve a profile/strategy against the live graph into a snapshot (CP-012).

The ``ExecutionProfileResolver`` folds a requested execution profile (or strategy)
against the live ``CapabilityGraph`` into a single ``ResolvedProfile`` snapshot the
runtime reads as a *decision input* — the convergence "KEY shift" from scattered
config to a resolved snapshot. The snapshot keeps the named profile's four levers
intact (so a profile means the same thing everywhere) and records *fallback notes*
when the environment cannot honour a posture (e.g. ``local_first`` routing with no
local provider) — it never silently rewrites the profile.

Layering (doc 58): L3. Imports the sibling L3 graph/profile models. The built-in
profile catalog (``capabilities.registry``) is imported lazily to avoid a
package-level import cycle (registry imports ``profiles.definition``).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.capabilities.graph import CapabilityGraph
from opencontext_core.profiles.definition import (
    ExecutionProfile,
    HarnessStrictness,
    ProviderRouting,
)
from opencontext_core.profiles.strategy import get_strategy

RESOLVED_PROFILE_SCHEMA_VERSION = "opencontext.resolved_profile.v1"


class ResolvedProfile(BaseModel):
    """A profile resolved against the live capability graph (a decision input)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = RESOLVED_PROFILE_SCHEMA_VERSION
    profile: ExecutionProfile = Field(description="The resolved execution profile.")
    strategy_id: str | None = Field(
        default=None, description="The strategy that selected the profile, if any."
    )
    capability_graph: CapabilityGraph = Field(description="The graph used for resolution.")
    fallbacks: list[str] = Field(
        default_factory=list,
        description="Recorded reasons a posture could not be fully honoured.",
    )

    # Convenience accessors so the runtime reads the four bound levers directly.
    @property
    def token_budget(self) -> int:
        return self.profile.token_budget

    @property
    def max_retries(self) -> int:
        return self.profile.max_retries

    @property
    def harness_strictness(self) -> HarnessStrictness:
        return self.profile.harness_strictness

    @property
    def provider_routing(self) -> ProviderRouting:
        return self.profile.provider_routing


class ExecutionProfileResolver:
    """Resolves a profile or strategy against a live ``CapabilityGraph`` (CP-012)."""

    def resolve(self, profile_id: str, graph: CapabilityGraph) -> ResolvedProfile:
        """Resolve ``profile_id`` against ``graph`` into a ``ResolvedProfile`` snapshot.

        An unknown ``profile_id`` (or empty string) coherently falls back to the
        default ``balanced`` profile with a recorded note rather than raising —
        the first run must always succeed (CP success criteria).
        """
        from opencontext_core.capabilities.registry import (
            BUILTIN_PROFILES,
            DEFAULT_PROFILE_ID,
        )

        fallbacks: list[str] = []
        profile = BUILTIN_PROFILES.get(profile_id)
        if profile is None:
            profile = BUILTIN_PROFILES[DEFAULT_PROFILE_ID]
            requested = profile_id or "<empty>"
            fallbacks.append(
                f"unknown execution profile {requested!r}; using default {DEFAULT_PROFILE_ID!r}."
            )

        fallbacks.extend(self._environment_fallbacks(profile, graph))
        return ResolvedProfile(profile=profile, capability_graph=graph, fallbacks=fallbacks)

    def resolve_strategy(self, strategy_id: str, graph: CapabilityGraph) -> ResolvedProfile:
        """Resolve a strategy id to its profile, then against ``graph`` (CP-009)."""
        strategy = get_strategy(strategy_id)
        if strategy is None:
            resolved = self.resolve(strategy_id, graph)
            resolved.fallbacks.insert(
                0, f"unknown execution strategy {strategy_id!r}; resolved as a profile id."
            )
            return resolved
        resolved = self.resolve(strategy.profile_id, graph)
        resolved.strategy_id = strategy.id
        return resolved

    @staticmethod
    def _environment_fallbacks(profile: ExecutionProfile, graph: CapabilityGraph) -> list[str]:
        """Record where the live environment cannot fully honour the profile posture."""
        notes: list[str] = []

        provider_nodes = [n for n in graph.nodes if n.kind == "provider"]
        real_provider = any(n.available and n.id != "provider.mock" for n in provider_nodes)
        local_provider = any(n.available and n.id in {"provider.ollama"} for n in provider_nodes)

        if not real_provider:
            notes.append(
                f"no live LLM provider detected; routing {profile.provider_routing!r} "
                f"will use the local/mock fallback."
            )
        if profile.provider_routing == "local_first" and not local_provider:
            notes.append(
                "local_first routing requested but no local provider detected; "
                "calls fall back to a remote provider."
            )
        if profile.harness_strictness == HarnessStrictness.strict and not graph.is_ready("pytest"):
            notes.append(
                "strict harness requested but no test runner detected; gates will run "
                "advisory until a test runner is installed."
            )
        return notes
