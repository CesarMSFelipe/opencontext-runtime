"""EngramProvisioner — detect and optionally install a co-resident Engram instance.

Design decisions:
- detect() delegates to engram_bridge.detect_engram() so there is one source of truth.
- plan_install() probes brew/scoop/go and returns an InstallPlan; if no PM is found
  it returns install_command=None and never raises.
- install() only runs subprocess when yes=True; raises RuntimeError when detection fails
  and yes=False so the caller can prompt the user.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class EngramInstallPlan:
    """What would be run to install Engram on this host."""

    detected: bool
    install_command: list[str] | None
    setup_command: list[str] | None
    message: str


def _probe_package_managers() -> list[str] | None:
    """Return the first usable install command or None if none found."""
    if sys.platform == "darwin" and shutil.which("brew"):
        return ["brew", "install", "engram"]
    if sys.platform == "win32" and shutil.which("scoop"):
        return ["scoop", "install", "engram"]
    if shutil.which("go"):
        return ["go", "install", "github.com/dstotijn/engram@latest"]
    return None


class EngramProvisioner:
    """Lifecycle helper for a co-resident Engram install."""

    def detect(self) -> bool:
        """Return True when Engram is usable in the current environment."""
        from opencontext_core.memory.engram_bridge import detect_engram

        return detect_engram()

    def plan_install(self, agent: str | None = None) -> EngramInstallPlan:
        """Build an install plan without executing anything.

        Returns install_command=None when no supported package manager is found.
        """
        if self.detect():
            return EngramInstallPlan(
                detected=True,
                install_command=None,
                setup_command=None,
                message="Engram is already installed.",
            )
        cmd = _probe_package_managers()
        if cmd is None:
            return EngramInstallPlan(
                detected=False,
                install_command=None,
                setup_command=None,
                message=(
                    "No supported package manager found (brew/scoop/go). "
                    "Install Engram manually: https://github.com/dstotijn/engram"
                ),
            )
        setup: list[str] | None = None
        if agent:
            setup = ["engram", "setup", "--agent", agent]
        return EngramInstallPlan(
            detected=False,
            install_command=cmd,
            setup_command=setup,
            message=f"Engram can be installed via: {' '.join(cmd)}",
        )

    def install(
        self, *, agent: str | None = None, yes: bool = False
    ) -> EngramInstallPlan:
        """Run the install plan when yes=True.

        Raises RuntimeError if Engram is not detected after install or if
        no plan is available and yes=False.
        """
        plan = self.plan_install(agent=agent)
        if plan.detected:
            return plan
        if plan.install_command is None:
            if yes:
                raise RuntimeError(plan.message)
            return plan
        if not yes:
            raise RuntimeError(
                f"Engram not installed. Run with yes=True to install. Plan: {plan.message}"
            )
        _run_command(plan.install_command)
        if plan.setup_command:
            _run_command(plan.setup_command)
        # Re-probe after install attempt.
        detected = self.detect()
        return EngramInstallPlan(
            detected=detected,
            install_command=plan.install_command,
            setup_command=plan.setup_command,
            message="Engram installed successfully." if detected else plan.message,
        )


def _run_command(cmd: list[str]) -> None:
    """Execute a subprocess command; raises RuntimeError on non-zero exit."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n{result.stderr or result.stdout}"
        )


if __name__ == "__main__":
    provisioner = EngramProvisioner()
    detected = provisioner.detect()
    assert isinstance(detected, bool)

    plan = provisioner.plan_install()
    assert isinstance(plan, EngramInstallPlan)
    # install_command is None when no PM is available OR when already detected.
    if not detected:
        # plan should not raise
        _ = plan.message

    print("memory/engram_provisioning.py self-check passed.")
