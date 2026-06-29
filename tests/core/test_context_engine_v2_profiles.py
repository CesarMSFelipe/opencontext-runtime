"""PR-010 SPEC-CTX-010-15: five context profiles."""

from __future__ import annotations

from opencontext_core.context.profiles import PROFILES, resolve_profile
from opencontext_core.models.context import ContextProfile


def test_five_profiles_exist() -> None:
    assert {p.value for p in ContextProfile} == {
        "balanced",
        "low-cost",
        "performance",
        "enterprise",
        "research",
    }
    assert set(PROFILES.keys()) == set(ContextProfile)


def test_unset_profile_resolves_to_balanced() -> None:
    assert resolve_profile(None) == PROFILES[ContextProfile.BALANCED]
    assert resolve_profile("not-a-profile") == PROFILES[ContextProfile.BALANCED]


def test_balanced_is_the_default_baseline() -> None:
    balanced = resolve_profile(ContextProfile.BALANCED)
    assert balanced.depth == 2
    assert balanced.compression == "balanced"
    assert balanced.memory_limit == 8
    assert balanced.file_threshold == 0.8


def test_low_cost_compresses_more_aggressively_than_balanced() -> None:
    low = resolve_profile("low-cost")
    balanced = resolve_profile("balanced")
    assert low.compression == "aggressive"
    assert balanced.compression == "balanced"
    # lower file-loading threshold than balanced
    assert low.file_threshold < balanced.file_threshold
    assert low.memory_limit < balanced.memory_limit


def test_profile_resolution_accepts_enum_and_string() -> None:
    assert resolve_profile("research").depth == resolve_profile(ContextProfile.RESEARCH).depth
