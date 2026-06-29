"""ExecutionProfile contracts and the five built-in profiles (CP-007, CP-008, CP-010)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.capabilities.registry import BUILTIN_PROFILES, builtin_profile_ids
from opencontext_core.profiles.definition import (
    EXECUTION_PROFILE_SCHEMA_VERSION,
    ExecutionProfile,
    HarnessStrictness,
)

EXPECTED_PROFILE_IDS = {"balanced", "low-cost", "enterprise", "research", "performance"}


def test_exactly_five_builtin_profiles() -> None:
    assert set(builtin_profile_ids()) == EXPECTED_PROFILE_IDS
    assert len(BUILTIN_PROFILES) == 5


def test_each_profile_binds_four_levers() -> None:
    for profile in BUILTIN_PROFILES.values():
        assert profile.schema_version == EXECUTION_PROFILE_SCHEMA_VERSION
        assert profile.token_budget > 0
        assert profile.max_retries >= 0
        assert isinstance(profile.harness_strictness, HarnessStrictness)
        assert profile.provider_routing in {"local_first", "remote_first", "policy"}


def test_low_cost_budget_strictly_smaller_than_performance() -> None:
    assert BUILTIN_PROFILES["low-cost"].token_budget < BUILTIN_PROFILES["performance"].token_budget


def test_enterprise_is_strict_blocking() -> None:
    assert BUILTIN_PROFILES["enterprise"].harness_strictness == HarnessStrictness.strict
    assert BUILTIN_PROFILES["enterprise"].provider_routing == "policy"


def test_profile_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ExecutionProfile(
            id="x",
            token_budget=10,
            max_retries=0,
            harness_strictness=HarnessStrictness.warn,
            provider_routing="policy",
            bogus=True,  # type: ignore[call-arg]
        )


def test_profile_rejects_nonpositive_budget() -> None:
    with pytest.raises(ValidationError):
        ExecutionProfile(
            id="x",
            token_budget=0,
            max_retries=0,
            harness_strictness=HarnessStrictness.warn,
            provider_routing="policy",
        )
