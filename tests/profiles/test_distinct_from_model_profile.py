"""Anti-regression: execution profiles are a distinct concept (CP-008).

The load-bearing distinction the spec demands is *execution profile* (budget /
retries / strictness / routing posture, PR-000.2) vs *model profile*
(``sdd_model_profile`` ∈ default/cheap/hybrid/premium, which picks an LLM per SDD
phase) vs install-time *setup presets/profiles*. These are different concepts that
must never be conflated in code.

Note: the string ``"enterprise"`` legitimately appears in BOTH the execution-
profile vocabulary and the setup *preset* vocabulary as different things, so this
test asserts type-distinctness for presets rather than a false string-disjointness
claim. The hard disjointness requirement is against the model-profile ids.
"""

from __future__ import annotations

from opencontext_core.capabilities.registry import BUILTIN_PROFILES
from opencontext_core.profiles.definition import ExecutionProfile
from opencontext_core.sdd_profiles import SDDProfile, SDDProfileManager
from opencontext_core.setup.presets import PRESET_CATALOG, PROFILE_CATALOG

EXECUTION_PROFILE_IDS = set(BUILTIN_PROFILES)


def test_execution_profile_ids_do_not_overlap_model_profile_ids() -> None:
    model_profile_ids = set(SDDProfileManager.DEFAULT_PROFILES)
    assert model_profile_ids == {"default", "cheap", "hybrid", "premium"}
    assert EXECUTION_PROFILE_IDS.isdisjoint(model_profile_ids)


def test_execution_profile_ids_do_not_overlap_setup_profile_ids() -> None:
    # setup PROFILE_CATALOG (developer/minimal/researcher/security-officer).
    assert EXECUTION_PROFILE_IDS.isdisjoint(set(PROFILE_CATALOG))


def test_execution_profile_is_a_distinct_type_from_model_and_setup_profiles() -> None:
    sample = BUILTIN_PROFILES["balanced"]
    assert isinstance(sample, ExecutionProfile)
    # Distinct types: not an SDD (model) profile and not a setup preset/profile.
    assert not isinstance(sample, SDDProfile)
    for preset in PRESET_CATALOG.values():
        assert not isinstance(preset, ExecutionProfile)
    for profile in PROFILE_CATALOG.values():
        assert not isinstance(profile, ExecutionProfile)


def test_execution_profile_carries_levers_model_profiles_lack() -> None:
    # The execution profile binds runtime levers a model profile has no concept of.
    sample = BUILTIN_PROFILES["balanced"]
    for lever in ("token_budget", "max_retries", "harness_strictness", "provider_routing"):
        assert hasattr(sample, lever)
    model_profile = SDDProfileManager.DEFAULT_PROFILES["default"]
    assert not any(
        hasattr(model_profile, lever)
        for lever in ("token_budget", "harness_strictness", "provider_routing")
    )
