"""wizard emits exact SecurityMode enum values.

RED first: ``onboarding/wizard.py`` offers ``cross_project`` / ``open`` security
choices and an ``air-gapped`` (hyphen) template, none of which are valid
``SecurityMode`` enum values, so the written config does not load.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config import SecurityMode, load_config
from opencontext_core.onboarding.service import OnboardingOptions, OnboardingService
from opencontext_core.onboarding.wizard import OnboardingWizard


def test_wizard_security_choices_are_valid_enum_values() -> None:
    """Every security choice the wizard can return must be a SecurityMode value."""
    wizard = OnboardingWizard(root=".")
    valid = {m.value for m in SecurityMode}
    choices = wizard.security_mode_choices()
    assert choices, "wizard exposed no security-mode choices"
    for choice in choices:
        assert choice in valid, f"wizard offers invalid security mode: {choice!r}"


def test_wizard_template_choices_are_valid() -> None:
    """Template choices must not include the hyphenated 'air-gapped' enum mismatch."""
    wizard = OnboardingWizard(root=".")
    templates = wizard.template_choices()
    assert "air-gapped" not in templates
    assert "air_gapped" in templates


def test_wizard_output_round_trips_through_load_config(tmp_path: Path) -> None:
    """A config written by the wizard (air-gapped) must load without raising."""
    wizard = OnboardingWizard(root=tmp_path)
    wizard.run(non_interactive=True, template="air_gapped", security_mode="air_gapped")

    config_path = tmp_path / "opencontext.yaml"
    assert config_path.exists()
    config = load_config(config_path)
    assert config.security.mode == SecurityMode.AIR_GAPPED


@pytest.mark.parametrize("mode", [m.value for m in SecurityMode])
def test_service_writes_loadable_config_for_every_mode(tmp_path: Path, mode: str) -> None:
    """OnboardingService output must load for every valid SecurityMode."""
    target = tmp_path / mode
    service = OnboardingService()
    service.run(OnboardingOptions(root=target, security_mode=mode, force_agent_files=True))
    config = load_config(target / "opencontext.yaml")
    assert config.security.mode == SecurityMode(mode)
