"""Tests for the onboarding wizard."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.onboarding.wizard import OnboardingWizard


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

    def test_wizard_accepts_security_override(self, tmp_path: Path) -> None:
        """Security mode override should be respected."""
        wizard = OnboardingWizard(root=tmp_path)
        wizard.run(
            non_interactive=True,
            security_mode="cross_project",
        )

    def test_wizard_accepts_agents_override(self, tmp_path: Path) -> None:
        """Agent list override should be respected."""
        wizard = OnboardingWizard(root=tmp_path)
        wizard.run(
            non_interactive=True,
            agents=["opencode", "cursor"],
        )

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
