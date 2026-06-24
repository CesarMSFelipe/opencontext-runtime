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
    """When no package manager is available, install_command=None and no exception."""
    provisioner = EngramProvisioner()
    with (
        patch.object(provisioner, "detect", return_value=False),
        patch("opencontext_core.memory.engram_provisioning._probe_package_managers", return_value=None),
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


def test_install_raises_when_not_detected_and_yes_false() -> None:
    provisioner = EngramProvisioner()
    with (
        patch.object(provisioner, "detect", return_value=False),
        patch("opencontext_core.memory.engram_provisioning._probe_package_managers",
              return_value=["brew", "install", "engram"]),
    ):
        try:
            provisioner.install(yes=False)
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


def test_install_plan_with_brew_has_command() -> None:
    provisioner = EngramProvisioner()
    with (
        patch.object(provisioner, "detect", return_value=False),
        patch("opencontext_core.memory.engram_provisioning._probe_package_managers",
              return_value=["brew", "install", "engram"]),
    ):
        plan = provisioner.plan_install()
    assert plan.install_command == ["brew", "install", "engram"]
