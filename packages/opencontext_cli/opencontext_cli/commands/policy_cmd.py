"""policy — inspect and simulate the unified Policy Engine (PR-005).

Usage:
  opencontext policy presets [--json]
  opencontext policy show [--json]
  opencontext policy simulate --command "<cmd>" [--preset <name>] [--ci] [--json]
  opencontext policy simulate --file <path> [--preset <name>] [--json]
  opencontext policy simulate --network [--preset <name>] [--json]

Surfaces the four selectable presets, the active posture, and a dry-run
``PolicyDecision`` for a candidate operation — without executing anything.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from opencontext_cli.output import eprint
from opencontext_core.config import load_config_or_defaults
from opencontext_core.dx.console_styles import console
from opencontext_core.policy.engine import PolicyEngine, PolicyOperation
from opencontext_core.policy.presets import (
    PRESET_TABLE,
    PolicyPreset,
    resolve_preset,
)


def add_policy_parser(subparsers: Any) -> None:
    """Add the ``policy`` command group."""
    policy_parser = subparsers.add_parser(
        "policy", help="Inspect and simulate the unified Policy Engine."
    )
    policy_subs = policy_parser.add_subparsers(dest="policy_action")

    presets_p = policy_subs.add_parser("presets", help="List the policy presets and postures.")
    presets_p.add_argument("--json", action="store_true", help="JSON output.")

    show_p = policy_subs.add_parser("show", help="Show the active preset and posture.")
    show_p.add_argument("--json", action="store_true", help="JSON output.")

    sim_p = policy_subs.add_parser("simulate", help="Dry-run a PolicyDecision for an operation.")
    # ``dest`` avoids colliding with the top-level ``command`` subparser dest.
    sim_p.add_argument(
        "--command", dest="sim_command", help="Command string to classify and evaluate."
    )
    sim_p.add_argument("--file", dest="file_path", help="File path to evaluate (forbidden-path).")
    sim_p.add_argument("--network", action="store_true", help="Evaluate a network operation.")
    sim_p.add_argument("--preset", help="Preset to simulate under (overrides config).")
    sim_p.add_argument("--ci", action="store_true", help="Simulate CI/remote (ask -> deny).")
    sim_p.add_argument("--json", action="store_true", help="JSON output.")


def handle_policy(args: Any) -> None:
    """Dispatch the ``policy`` sub-command."""
    action = getattr(args, "policy_action", None)
    if action == "presets":
        _handle_presets(args)
        return
    if action == "show":
        _handle_show(args)
        return
    if action == "simulate":
        _handle_simulate(args)
        return
    eprint("Usage: opencontext policy [presets|show|simulate]")
    sys.exit(1)


def _handle_presets(args: Any) -> None:
    rows = [
        {"preset": preset.value, **posture.model_dump()} for preset, posture in PRESET_TABLE.items()
    ]
    if getattr(args, "json", False):
        print(json.dumps(rows, indent=2))  # pure JSON to stdout
        return
    console.header("Policy Presets")
    table_rows = [
        [
            row["preset"] + (" (default)" if row["preset"] == PolicyPreset.BALANCED.value else ""),
            str(row["network"]),
            str(row["external_provider"]),
            str(row["high_risk_write"]),
            str(row["unknown_command"]),
            str(row["redact_secrets"]),
            str(row["command_enforcement"]),
            str(row["cache_ceiling"]),
        ]
        for row in rows
    ]
    console.table(
        "Presets",
        [
            "Preset",
            "Network",
            "Provider",
            "High-Risk Write",
            "Unknown Cmd",
            "Redact",
            "Enforcement",
            "Cache Ceiling",
        ],
        table_rows,
    )


def _handle_show(args: Any) -> None:
    config = load_config_or_defaults()
    engine = PolicyEngine(config=config)
    posture = PRESET_TABLE[engine.preset]
    payload = {
        "preset": engine.preset.value,
        "ci_mode": engine.ci_mode,
        "posture": posture.model_dump(),
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))  # pure JSON to stdout
        return
    console.header("Policy")
    console.section("Active posture")
    console.print(f"Active preset: {engine.preset.value}")
    console.print(f"CI/remote mode: {engine.ci_mode}")
    console.print(f"Network: {posture.network}")
    console.print(f"External provider: {posture.external_provider}")
    console.print(f"Unknown command: {posture.unknown_command}")
    console.print(f"Command enforcement: {posture.command_enforcement}")
    console.print(f"Cache ceiling: {posture.cache_ceiling}")


def _handle_simulate(args: Any) -> None:
    config = load_config_or_defaults()
    preset_name = getattr(args, "preset", None)
    preset = resolve_preset(preset_name) if preset_name else None
    engine = PolicyEngine(config=config, preset=preset, ci_mode=getattr(args, "ci", False))

    command = getattr(args, "sim_command", None)
    file_path = getattr(args, "file_path", None)
    if command:
        operation = PolicyOperation(kind="command", command=command)
    elif file_path:
        operation = PolicyOperation(kind="file", target_path=file_path)
    elif getattr(args, "network", False):
        operation = PolicyOperation(kind="network")
    else:
        eprint("Specify one of --command, --file, or --network.")
        sys.exit(1)

    decision = engine.evaluate(operation)
    if getattr(args, "json", False):
        print(decision.model_dump_json(indent=2))  # pure JSON to stdout
        return
    console.header("Policy Simulation")
    console.print(f"operation:   {decision.operation}")
    console.print(f"decision:    {decision.decision}")
    console.print(f"reason:      {decision.reason}")
    console.print(f"policy_id:   {decision.policy_id}")
    console.print(f"mode:        {decision.mode}")
    if decision.evidence_refs:
        console.print(f"evidence:    {', '.join(decision.evidence_refs)}")
    if decision.remediation:
        console.print(f"remediation: {decision.remediation}")
