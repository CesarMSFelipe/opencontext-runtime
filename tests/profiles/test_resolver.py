"""ExecutionProfileResolver folds a profile against the live graph (CP-012)."""

from __future__ import annotations

from opencontext_core.capabilities.graph import CapabilityGraph, CapabilityNode
from opencontext_core.profiles.definition import HarnessStrictness
from opencontext_core.profiles.resolver import (
    RESOLVED_PROFILE_SCHEMA_VERSION,
    ExecutionProfileResolver,
    ResolvedProfile,
)


def _no_provider_graph() -> CapabilityGraph:
    # Only a mock provider -> no real/local provider available.
    return CapabilityGraph(
        nodes=[
            CapabilityNode(id="pytest", kind="test", available=True),
            CapabilityNode(id="provider.mock", kind="provider", available=False),
        ]
    )


def test_resolve_returns_snapshot_binding_four_levers() -> None:
    resolver = ExecutionProfileResolver()
    resolved = resolver.resolve("balanced", _no_provider_graph())

    assert isinstance(resolved, ResolvedProfile)
    assert resolved.schema_version == RESOLVED_PROFILE_SCHEMA_VERSION
    assert resolved.profile.id == "balanced"
    # Convenience accessors expose the bound levers as a single decision input.
    assert resolved.token_budget == resolved.profile.token_budget
    assert resolved.max_retries == resolved.profile.max_retries
    assert resolved.harness_strictness == resolved.profile.harness_strictness
    assert resolved.provider_routing == resolved.profile.provider_routing


def test_performance_with_no_local_provider_keeps_remote_and_records_fallback() -> None:
    resolver = ExecutionProfileResolver()
    resolved = resolver.resolve("performance", _no_provider_graph())

    # Routing posture is preserved (the snapshot never silently rewrites the profile).
    assert resolved.provider_routing == "remote_first"
    # ...but the unmet environment is recorded as a fallback note.
    assert resolved.fallbacks
    assert any("provider" in note for note in resolved.fallbacks)


def test_enterprise_yields_strict_harness_strictness() -> None:
    resolved = ExecutionProfileResolver().resolve("enterprise", _no_provider_graph())
    assert resolved.harness_strictness == HarnessStrictness.strict


def test_unknown_profile_falls_back_to_balanced_with_note() -> None:
    resolved = ExecutionProfileResolver().resolve("does-not-exist", _no_provider_graph())
    assert resolved.profile.id == "balanced"
    assert any("unknown execution profile" in note for note in resolved.fallbacks)


def test_empty_profile_id_falls_back_to_default() -> None:
    resolved = ExecutionProfileResolver().resolve("", _no_provider_graph())
    assert resolved.profile.id == "balanced"


def test_resolve_strategy_maps_to_profile_and_records_strategy_id() -> None:
    resolved = ExecutionProfileResolver().resolve_strategy("fast", _no_provider_graph())
    assert resolved.strategy_id == "fast"
    assert resolved.profile.id == "performance"


def test_local_first_strategy_records_local_fallback_when_no_local_provider() -> None:
    resolved = ExecutionProfileResolver().resolve_strategy("local_first", _no_provider_graph())
    assert resolved.profile.provider_routing == "local_first"
    assert any("local_first" in note for note in resolved.fallbacks)
