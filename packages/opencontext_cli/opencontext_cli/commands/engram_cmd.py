"""Engram CLI subcommand — doctor, install, setup."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any


def add_engram_parser(subparsers: Any) -> None:
    """Register the ``engram`` subparser tree."""
    engram_parser = subparsers.add_parser(
        "engram",
        help="Manage the co-resident Engram memory instance.",
        description=(
            "Commands for detecting, installing, and configuring Engram.\n\n"
            "  opencontext engram doctor [--json]     Check Engram status\n"
            "  opencontext engram install [--yes]     Install Engram if missing\n"
            "  opencontext engram setup <agent>       Wire Engram to an agent\n"
        ),
    )
    engram_sub = engram_parser.add_subparsers(dest="engram_command", required=True)

    # doctor
    doctor_p = engram_sub.add_parser("doctor", help="Show Engram detection status.")
    doctor_p.add_argument("--agent", default=None, help="Target agent name.")
    doctor_p.add_argument("--json", action="store_true", help="Emit JSON output.")

    # install
    install_p = engram_sub.add_parser("install", help="Install Engram if not already present.")
    install_p.add_argument("--agent", default=None, help="Agent to configure after install.")
    install_p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation.")

    # setup
    setup_p = engram_sub.add_parser("setup", help="Run engram setup for an agent.")
    setup_p.add_argument("agent", help="Agent name (e.g. claude-code, opencode).")


def handle_engram(args: Any) -> int:
    """Dispatch engram subcommand; returns exit code."""
    cmd = getattr(args, "engram_command", None)
    if cmd == "doctor":
        return _doctor(args)
    if cmd == "install":
        return _install(args)
    if cmd == "setup":
        return _setup(args)
    print(f"Unknown engram subcommand: {cmd}", file=sys.stderr)
    return 1


def _doctor(args: Any) -> int:
    """Report Engram detection status."""
    from opencontext_core.memory.engram_provisioning import EngramProvisioner

    agent = getattr(args, "agent", None)
    json_out = getattr(args, "json", False)
    provisioner = EngramProvisioner()
    plan = provisioner.plan_install(agent=agent)

    if json_out:
        data: dict[str, Any] = {
            "detected": plan.detected,
            "install_command": plan.install_command,
            "setup_command": plan.setup_command,
            "message": plan.message,
        }
        print(json.dumps(data))
    else:
        status = "detected" if plan.detected else "not detected"
        print(f"Engram: {status}")
        print(f"  {plan.message}")
        if plan.install_command:
            print(f"  Install: {' '.join(plan.install_command)}")
        if plan.setup_command:
            print(f"  Setup: {' '.join(plan.setup_command)}")
    return 0


def _install(args: Any) -> int:
    """Install Engram if not already detected."""
    from opencontext_core.memory.engram_provisioning import EngramProvisioner

    agent = getattr(args, "agent", None)
    yes = getattr(args, "yes", False)
    provisioner = EngramProvisioner()
    try:
        result = provisioner.install(agent=agent, yes=yes)
        if result.detected:
            print("Engram is ready.")
        else:
            print(f"Engram install result: {result.message}")
    except RuntimeError as exc:
        print(f"Engram install failed: {exc}", file=sys.stderr)
        return 1
    return 0


def _setup(args: Any) -> int:
    """Run engram setup for an agent."""
    agent = getattr(args, "agent", "")
    if not agent:
        print("Error: agent name required.", file=sys.stderr)
        return 1
    cmd = ["engram", "setup", agent]
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode


if __name__ == "__main__":
    import argparse

    _p = argparse.ArgumentParser()
    _sub = _p.add_subparsers()
    add_engram_parser(_sub)
    _a = _p.parse_args(["doctor", "--json"])
    sys.exit(handle_engram(_a))
