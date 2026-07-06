"""Product-contract maturity classification for every top-level CLI command.

This is the Sprint 2 truth layer: "stable" is the supported product surface
(documented lifecycle commands users and CI may rely on), "preview" is
functional but evolving, "internal" is developer-facing diagnostics/plumbing.
It intentionally holds a much smaller stable set than the older visibility map
in ``opencontext_cli.command_maturity``.
"""

from __future__ import annotations

from typing import Final, Literal

Maturity = Literal["stable", "preview", "internal"]

MATURITIES: Final[frozenset[str]] = frozenset({"stable", "preview", "internal"})

COMMAND_MATURITY: Final[dict[str, Maturity]] = {
    # --- stable: the supported product surface ---
    "clean": "stable",
    "config": "stable",
    "doctor": "stable",
    "harness": "stable",
    "index": "stable",
    "init": "stable",
    "install": "stable",
    "knowledge-graph": "stable",
    "memory": "stable",
    "pack": "stable",
    "run": "stable",
    "runs": "stable",
    "sdd": "stable",
    "status": "stable",
    "tui": "stable",  # contract-stable; the command ships in a later sprint
    "uninstall": "stable",
    "version": "stable",
    # --- preview: functional but evolving ---
    "agent": "preview",
    "agent-harness": "preview",
    "architecture": "preview",
    "benchmark": "preview",
    "bridges": "preview",
    "capabilities": "preview",
    "clarify": "preview",
    "context": "preview",  # alias -> verified-context
    "contract": "preview",
    "decision-log": "preview",
    "decisions": "preview",
    "demo": "preview",
    "engram": "preview",
    "explain": "preview",
    "health": "preview",
    "kg": "preview",  # alias -> knowledge-graph
    "loop": "preview",
    "maturity": "preview",
    "mcp": "preview",
    "models": "preview",
    "oc-new": "preview",
    "persona": "preview",
    "plugin": "preview",
    "policy": "preview",
    "preset": "preview",
    "privacy": "preview",
    "profile": "preview",
    "prompt": "preview",
    "receipt": "preview",
    "review": "preview",
    "routes": "preview",
    "security": "preview",
    "session": "preview",
    "setup": "preview",
    "simulate": "preview",
    "skill": "preview",
    "skill-registry": "preview",
    "stack": "preview",
    "storage": "preview",
    "studio": "preview",
    "sync": "preview",
    "telemetry": "preview",
    "tokens": "preview",
    "update": "preview",
    "upgrade": "preview",
    "verified-context": "preview",
    "verify": "preview",
    # --- internal: developer-facing diagnostics and plumbing ---
    "agent-context": "internal",
    "aicx": "internal",
    "approvals": "internal",
    "ask": "internal",
    "bytecode": "internal",
    "cache": "internal",
    "checkpoint": "internal",
    "ci-check": "internal",
    "command": "internal",
    "eval": "internal",
    "evolve": "internal",
    "extension": "internal",
    "git": "internal",
    "hints": "internal",
    "inspect": "internal",
    "instructions": "internal",
    "learn": "internal",
    "mutation": "internal",
    "onboard": "internal",
    "org": "internal",
    "playbooks": "internal",
    "provider": "internal",
    "quality": "internal",
    "release": "internal",
    "report": "internal",
    "trace": "internal",
    "watch": "internal",
    "workflow": "internal",
    "workflows": "internal",
}


def maturity(command: str) -> str:
    """Contract maturity for *command*; unknown commands default to ``preview``."""
    return COMMAND_MATURITY.get(command, "preview")
