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


def test_no_go_toolchain_degrades_gracefully() -> None:
    """No Engram and no Go toolchain → None command with actionable guidance."""
    provisioner = EngramProvisioner()
    with (
        patch.object(provisioner, "detect", return_value=False),
        patch("shutil.which", return_value=None),
    ):
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


def test_install_when_not_detected_no_go_returns_plan_with_guidance() -> None:
    """install() with no automated command returns a plan with a helpful message."""
    provisioner = EngramProvisioner()
    with (
        patch.object(provisioner, "detect", return_value=False),
        patch("shutil.which", return_value=None),
    ):
        plan = provisioner.install(yes=False)
    assert plan.install_command is None
    assert plan.detected is False
    assert "install" in plan.message.lower()


def test_install_command_uses_go_when_available() -> None:
    """With a Go toolchain, the automated install is `go install` of the Engram module."""
    provisioner = EngramProvisioner()
    with (
        patch.object(provisioner, "detect", return_value=False),
        patch("shutil.which", return_value="/usr/bin/go"),
    ):
        plan = provisioner.plan_install()
    assert plan.install_command == [
        "go",
        "install",
        "github.com/Gentleman-Programming/engram/cmd/engram@latest",
    ]
    assert plan.detected is False
