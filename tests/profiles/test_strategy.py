"""The six built-in execution strategies map onto profiles (CP-009)."""

from __future__ import annotations

from opencontext_core.capabilities.registry import BUILTIN_PROFILES
from opencontext_core.profiles.strategy import BUILTIN_STRATEGIES, builtin_strategy_ids

EXPECTED_STRATEGY_IDS = {"fast", "cheap", "careful", "enterprise", "research", "local_first"}


def test_exactly_six_strategies() -> None:
    assert set(builtin_strategy_ids()) == EXPECTED_STRATEGY_IDS
    assert len(BUILTIN_STRATEGIES) == 6


def test_each_strategy_maps_to_a_valid_profile() -> None:
    for strategy in BUILTIN_STRATEGIES.values():
        assert strategy.profile_id in BUILTIN_PROFILES, (
            f"strategy {strategy.id} maps to unknown profile {strategy.profile_id}"
        )


def test_local_first_strategy_routes_local_first() -> None:
    strategy = BUILTIN_STRATEGIES["local_first"]
    profile = BUILTIN_PROFILES[strategy.profile_id]
    assert profile.provider_routing == "local_first"


def test_strategy_to_profile_mapping_is_stable() -> None:
    assert BUILTIN_STRATEGIES["fast"].profile_id == "performance"
    assert BUILTIN_STRATEGIES["cheap"].profile_id == "low-cost"
    assert BUILTIN_STRATEGIES["careful"].profile_id == "enterprise"
    assert BUILTIN_STRATEGIES["enterprise"].profile_id == "enterprise"
    assert BUILTIN_STRATEGIES["research"].profile_id == "research"
    assert BUILTIN_STRATEGIES["local_first"].profile_id == "low-cost"
