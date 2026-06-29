"""PROD-005 / B5 — CLI surface anti-regression guard.

The ``opencontext architecture`` command was added ADDITIVELY. This guard makes
"additive" enforceable: the frozen set of pre-existing top-level commands
(:data:`KNOWN_COMMANDS`) MUST remain a subset of the live CLI surface — no command
may be removed or renamed — and the new ``architecture`` command MUST be present.

If you intentionally add a command, add it to :data:`KNOWN_COMMANDS`. If you must
remove/rename one, that is a CLI contract break and requires an explicit, reviewed
update here (same ratchet philosophy as the layering/contract baselines).
"""

from __future__ import annotations

import argparse

from opencontext_cli.main import _build_parser

#: Frozen snapshot of the top-level command surface that existed before B5. The live
#: surface must stay a SUPERSET of this set (additive-only).
KNOWN_COMMANDS: frozenset[str] = frozenset(
    {
        "agent",
        "agent-context",
        "aicx",
        "approvals",
        "ask",
        "benchmark",
        "bridges",
        "bytecode",
        "cache",
        "capabilities",
        "checkpoint",
        "ci-check",
        "clarify",
        "clean",
        "command",
        "config",
        "context",
        "contract",
        "decision-log",
        "decisions",
        "demo",
        "doctor",
        "engram",
        "eval",
        "evolve",
        "explain",
        "extension",
        "git",
        "harness",
        "health",
        "hints",
        "index",
        "init",
        "inspect",
        "install",
        "instructions",
        "kg",
        "knowledge-graph",
        "learn",
        "loop",
        "maturity",
        "mcp",
        "memory",
        "models",
        "mutation",
        "oc-new",
        "onboard",
        "org",
        "pack",
        "persona",
        "playbooks",
        "plugin",
        "policy",
        "preset",
        "privacy",
        "profile",
        "prompt",
        "provider",
        "quality",
        "receipt",
        "release",
        "report",
        "review",
        "routes",
        "run",
        "runs",
        "security",
        "session",
        "setup",
        "simulate",
        "skill",
        "skill-registry",
        "stack",
        "status",
        "studio",
        "sync",
        "telemetry",
        "tokens",
        "trace",
        "uninstall",
        "update",
        "upgrade",
        "verified-context",
        "verify",
        "version",
        "watch",
        "workflow",
        "workflows",
    }
)


def _top_level_commands() -> set[str]:
    parser = _build_parser()
    commands: set[str] = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            commands.update(action.choices.keys())
    return commands


def test_no_existing_command_removed() -> None:
    """Every pre-existing top-level command still exists (additive-only surface)."""
    live = _top_level_commands()
    removed = KNOWN_COMMANDS - live
    assert not removed, f"CLI commands removed/renamed (contract break): {sorted(removed)}"


def test_architecture_command_added() -> None:
    """The B5 ``architecture`` command is registered."""
    assert "architecture" in _top_level_commands()
