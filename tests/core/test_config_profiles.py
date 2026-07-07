"""PR-013 SPEC-CLI-013-02: five built-in config profiles."""

from __future__ import annotations

from opencontext_core import config_profiles
from opencontext_core.config import OpenContextConfig, default_config_data


def test_builtin_profiles_present_with_balanced_default() -> None:
    names = {p["name"] for p in config_profiles.list_profiles()}
    assert names == {
        "balanced",
        "low-cost",
        "enterprise",
        "research",
        "performance",
        "default",
        "ci",
        "local",
        "agent",
    }
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


# ── Runtime-mode profiles (plan §6): ci / local / agent ─────────────────────


def _merged_config(profile: str) -> OpenContextConfig:
    from opencontext_core.config import _deep_merge

    merged = _deep_merge(default_config_data(), config_profiles.get_profile(profile))
    return OpenContextConfig.model_validate(merged)


def test_ci_profile_disables_interactivity() -> None:
    config = _merged_config("ci")
    assert config.interface.interactive is False
    assert config.interface.tui is False
    assert config.interface.json_default is True


def test_local_profile_enables_interactivity() -> None:
    config = _merged_config("local")
    assert config.interface.interactive is True
    assert config.interface.tui is True


def test_agent_profile_requires_approval_and_bounds_context() -> None:
    config = _merged_config("agent")
    assert config.harness.approval_required_for_writes is True
    assert config.context.max_input_tokens == 24000
