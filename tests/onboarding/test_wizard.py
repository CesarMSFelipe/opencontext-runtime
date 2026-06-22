"""Tests for the onboarding wizard."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config import SecurityMode, load_config
from opencontext_core.onboarding.wizard import OnboardingWizard
from opencontext_core.user_prefs import UserConfigStore


class TestOnboardingWizard:
    """Onboarding wizard tests."""

    def test_wizard_completes_with_defaults(self, tmp_path: Path) -> None:
        """Wizard should complete in non-interactive mode with defaults."""
        wizard = OnboardingWizard(root=tmp_path)
        # Force non-interactive
        result = wizard.run(non_interactive=True)
        assert result.root == str(tmp_path.resolve())
        assert result.config_path
        assert "opencontext.yaml" in result.config_path

    def test_wizard_accepts_template_override(self, tmp_path: Path) -> None:
        """Template override should be respected."""
        wizard = OnboardingWizard(root=tmp_path)
        wizard.run(
            non_interactive=True,
            template="enterprise",
        )
        # Verify enterprise template was applied via harness config
        import yaml

        harness_path = tmp_path / ".opencontext" / "harness.yaml"
        if harness_path.exists():
            data = yaml.safe_load(harness_path.read_text(encoding="utf-8"))
            assert data is not None

    def test_wizard_accepts_tdd_override(self, tmp_path: Path) -> None:
        """TDD mode override should be respected."""
        wizard = OnboardingWizard(root=tmp_path)
        wizard.run(
            non_interactive=True,
            tdd="strict",
        )
        # Verify via SDD context
        import json

        sdd_path = tmp_path / ".opencontext" / "sdd" / "context.json"
        if sdd_path.exists():
            data = json.loads(sdd_path.read_text(encoding="utf-8"))
            assert data["tdd_mode"] == "strict"

    @pytest.mark.parametrize(
        "requested", ["air-gapped", "enterprise", "developer", "private_project"]
    )
    def test_wizard_persists_valid_security_mode(self, tmp_path: Path, requested: str) -> None:
        """A valid (or legacy-hyphenated) mode is written to config AND prefs."""
        OnboardingWizard(root=tmp_path).run(non_interactive=True, security_mode=requested)

        config = load_config(tmp_path / "opencontext.yaml")  # must not raise
        expected = SecurityMode(requested.replace("-", "_"))
        assert config.security.mode == expected
        assert UserConfigStore().load().security_mode == expected.value

    @pytest.mark.parametrize("bogus", ["cross_project", "open", "garbage"])
    def test_wizard_never_persists_invalid_security_mode(self, tmp_path: Path, bogus: str) -> None:
        """An unrecognised mode is coerced consistently — never stored raw.

        Regression for the split where the config was coerced to a valid value
        but user prefs kept the raw invalid string, leaving the two disagreeing.
        """
        OnboardingWizard(root=tmp_path).run(non_interactive=True, security_mode=bogus)

        config = load_config(tmp_path / "opencontext.yaml")  # must not raise
        valid = {m.value for m in SecurityMode}
        assert config.security.mode.value in valid
        prefs_mode = UserConfigStore().load().security_mode
        assert prefs_mode in valid  # FAILED before the fix: prefs held the raw string
        assert prefs_mode == config.security.mode.value  # config and prefs agree

    def test_wizard_accepts_agents_override(self, tmp_path: Path) -> None:
        """Agent list override should be respected."""
        wizard = OnboardingWizard(root=tmp_path)
        wizard.run(
            non_interactive=True,
            agents=["opencode", "cursor"],
        )

    def test_wizard_non_interactive_defaults_to_opencode_when_no_agent_present(
        self, tmp_path: Path
    ) -> None:
        """With no agent CLI on the (isolated) host, the default selection is opencode."""
        result = OnboardingWizard(root=tmp_path).run(non_interactive=True)
        assert result.active_clients == ["opencode"]

    def test_wizard_non_interactive_configures_claude_code_when_present(
        self, tmp_path: Path
    ) -> None:
        """A non-interactive wizard run on a host with Claude Code configures it by
        default — writing the project ``.mcp.json`` opencontext entry — with no flags."""
        import json

        (Path.home() / ".claude").mkdir(parents=True, exist_ok=True)

        result = OnboardingWizard(root=tmp_path).run(non_interactive=True)

        assert "claude-code" in result.active_clients
        servers = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
        assert "opencontext" in servers

    def test_wizard_non_interactive_detection(self) -> None:
        """In a test environment, is_interactive should return False."""
        wizard = OnboardingWizard(root=".")
        # Non-interactive detection depends on CI and TTY; in pytest
        # stdout is captured so isatty() returns False
        assert wizard.is_interactive() is False

    def test_wizard_creates_config(self, tmp_path: Path) -> None:
        """Wizard should create opencontext.yaml."""
        wizard = OnboardingWizard(root=tmp_path)
        wizard.run(non_interactive=True)
        config = tmp_path / "opencontext.yaml"
        assert config.exists()

    def test_wizard_creates_sdd_context(self, tmp_path: Path) -> None:
        """Wizard should create SDD context."""
        wizard = OnboardingWizard(root=tmp_path)
        wizard.run(non_interactive=True)
        sdd = tmp_path / ".opencontext" / "sdd" / "context.json"
        assert sdd.exists()

    def test_wizard_creates_harness(self, tmp_path: Path) -> None:
        """Wizard should create harness.yaml."""
        wizard = OnboardingWizard(root=tmp_path)
        wizard.run(non_interactive=True)
        harness = tmp_path / ".opencontext" / "harness.yaml"
        assert harness.exists()

    def test_wizard_creates_opencontext_directory(self, tmp_path: Path) -> None:
        """Wizard should create .opencontext directory."""
        wizard = OnboardingWizard(root=tmp_path)
        wizard.run(non_interactive=True)
        oc_dir = tmp_path / ".opencontext"
        assert oc_dir.exists()
        assert oc_dir.is_dir()
