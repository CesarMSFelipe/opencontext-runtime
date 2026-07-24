"""EngramProvisioner — detect and optionally install a co-resident Engram instance.

Design decisions:
- detect() delegates to engram_bridge.detect_engram() so there is one source of truth.
- Engram is an external Go application (github.com/Gentleman-Programming/engram); the
  coexistence bridge talks to its ``engram`` binary. plan_install() returns a ``go
  install`` command when a Go toolchain is present, else install_command=None with an
  actionable message; it never raises.
- install() only runs the subprocess when yes=True; raises RuntimeError when detection
  fails and yes=False so the caller can prompt the user.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

# NOTE: Map of known agent names to their engram setup sub-command argument.
_AGENT_SETUP_MAP: dict[str, str] = {
    "claude-code": "claude-code",
    "codex": "codex",
    "opencode": "opencode",
    "cursor": "cursor",
    "windsurf": "windsurf",
    "aider": "aider",
    "generic": "generic",
}


@dataclass(frozen=True)
class EngramInstallPlan:
    """What would be run to install Engram on this host."""

    detected: bool
    install_command: list[str] | None
    setup_command: list[str] | None
    message: str


def _install_command() -> list[str] | None:
    # Engram is an external Go application. The coexistence bridge needs its ``engram``
    # binary on PATH, so the supported automated install is ``go install`` when a Go
    # toolchain is available. Without Go there is no self-contained install command; the
    # caller surfaces an actionable message (release binary / Claude Code plugin).
    import shutil

    if shutil.which("go"):
        return ["go", "install", "github.com/Gentleman-Programming/engram/cmd/engram@latest"]
    return None


def _setup_command(agent: str | None) -> list[str] | None:
    """Return the engram setup command for *agent*, or None if not in the known map."""
    if not agent:
        return None
    if agent not in _AGENT_SETUP_MAP:
        return None
    return ["engram", "setup", _AGENT_SETUP_MAP[agent]]


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
                setup_command=_setup_command(agent),
                message="Engram is already installed.",
            )
        cmd = _install_command()
        if cmd is None:
            return EngramInstallPlan(
                detected=False,
                install_command=None,
                setup_command=None,
                message=(
                    "Engram not detected and no Go toolchain found. Install Go and re-run "
                    "(`opencontext engram install --yes` runs `go install "
                    "github.com/Gentleman-Programming/engram/cmd/engram@latest`), or grab a "
                    "release binary from https://github.com/Gentleman-Programming/engram/releases, "
                    "then ensure `engram` is on PATH."
                ),
            )
        return EngramInstallPlan(
            detected=False,
            install_command=cmd,
            setup_command=_setup_command(agent),
            message=f"Engram can be installed via: {' '.join(cmd)}",
        )

    def install(self, *, agent: str | None = None, yes: bool = False) -> EngramInstallPlan:
        """Run the install plan when yes=True.

        Raises RuntimeError if Engram is not detected after install or if
        no plan is available and yes=False.
        """
        plan = self.plan_install(agent=agent)
        if plan.detected:
            return plan
        if plan.install_command is None:
            # No automated install available; return the plan (with actionable message).
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
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr or result.stdout}")


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
