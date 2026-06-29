"""PR-013 SPEC-CLI-013-02: five built-in config profiles."""

from __future__ import annotations

from opencontext_core import config_profiles
from opencontext_core.config import OpenContextConfig, default_config_data


def test_five_profiles_present_with_balanced_default() -> None:
    names = {p["name"] for p in config_profiles.list_profiles()}
    assert names == {"balanced", "low-cost", "enterprise", "research", "performance"}
    assert config_profiles.DEFAULT_PROFILE == "balanced"
    # balanced is listed first.
    assert config_profiles.list_profiles()[0]["name"] == "balanced"


def test_enterprise_overlay_applies_strict_defaults() -> None:
    overlay = config_profiles.get_profile("enterprise")
    merged = {**default_config_data(), **overlay}
    config = OpenContextConfig.model_validate(merged)
    assert config.security.mode.value == "enterprise"
    assert config.harness.approval_required_for_writes is True
    assert config.providers.strategy == "enterprise"


def test_unknown_profile_raises() -> None:
    import pytest

    with pytest.raises(KeyError):
        config_profiles.get_profile("does-not-exist")
