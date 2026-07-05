"""Tests for EngramProvisioner — spec §Domain 4."""

from __future__ import annotations

from unittest.mock import patch

from opencontext_core.memory.engram_provisioning import EngramInstallPlan, EngramProvisioner


def test_detect_returns_bool() -> None:
    provisioner = EngramProvisioner()
    result = provisioner.detect()
    assert isinstance(result, bool)


def test_plan_install_returns_install_plan() -> None:
    provisioner = EngramProvisioner()
    plan = provisioner.plan_install()
    assert isinstance(plan, EngramInstallPlan)
    assert isinstance(plan.message, str)
    assert isinstance(plan.detected, bool)


def test_no_pm_degrades_gracefully() -> None:
    """Engram has no automated install; plan_install returns None command with guidance."""
    provisioner = EngramProvisioner()
    with patch.object(provisioner, "detect", return_value=False):
        plan = provisioner.plan_install()
    assert plan.install_command is None
    assert plan.detected is False
    assert plan.message  # non-empty guidance


def test_already_detected_returns_detected_plan() -> None:
    provisioner = EngramProvisioner()
    with patch.object(provisioner, "detect", return_value=True):
        plan = provisioner.plan_install()
    assert plan.detected is True
    assert plan.install_command is None
    assert "already" in plan.message.lower()


def test_install_when_not_detected_returns_plan_with_guidance() -> None:
    """install() with no automated command returns a plan with a helpful message."""
    provisioner = EngramProvisioner()
    with patch.object(provisioner, "detect", return_value=False):
        plan = provisioner.install(yes=False)
    assert plan.install_command is None
    assert plan.detected is False
    assert "plugin" in plan.message.lower() or "install" in plan.message.lower()


def test_install_plan_has_no_automated_command() -> None:
    """No automated install path exists; users install via Claude Code plugin mechanism."""
    provisioner = EngramProvisioner()
    with patch.object(provisioner, "detect", return_value=False):
        plan = provisioner.plan_install()
    assert plan.install_command is None
