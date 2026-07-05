"""Per-command API maturity classification (stable / preview / internal).

Public-vs-hidden (argparse.SUPPRESS) is a *visibility* knob, not a *stability*
one — some hidden commands are stable (they appear in the epilog routes), and some
visible commands are still evolving. This map expresses the API-stability contract
so users know what they can rely on. Kept dependency-free so both the CLI and the
completeness test can import it without a circular import through main.py.
"""

from __future__ import annotations

from typing import Final, Literal

Maturity = Literal["stable", "preview", "internal"]

MATURITIES: Final[frozenset[str]] = frozenset({"stable", "preview", "internal"})

COMMAND_MATURITY: Final[dict[str, Maturity]] = {
    # --- stable: documented lifecycle + epilog-route commands ---
    "agent": "stable",
    "aicx": "stable",
    "benchmark": "stable",
    "capabilities": "stable",
    "ci-check": "stable",
    "clarify": "stable",
    "clean": "stable",
    "config": "stable",
    "demo": "stable",
    "doctor": "stable",
    "engram": "stable",
    "explain": "stable",
    "harness": "stable",
    "health": "stable",
    "index": "stable",
    "init": "stable",
    "install": "stable",
    "knowledge-graph": "stable",
    "loop": "stable",
    "maturity": "stable",
    "mcp": "stable",
    "memory": "stable",
    "models": "stable",
    "pack": "stable",
    "persona": "stable",
    "plugin": "stable",
    "privacy": "stable",
    "prompt": "stable",
    "receipt": "stable",
    "run": "stable",
    "runs": "stable",
    "security": "stable",
    "session": "stable",
    "setup": "stable",
    "skill": "stable",
    "skill-registry": "stable",
    "status": "stable",
    "sync": "stable",
    "tokens": "stable",
    "uninstall": "stable",
    "update": "stable",
    "upgrade": "stable",
    "verified-context": "stable",
    "verify": "stable",
    "version": "stable",
    "workflow": "stable",
    "kg": "stable",  # alias -> knowledge-graph
    "context": "stable",  # alias -> verified-context
    # --- preview: functional but evolving subsystems ---
    "agent-context": "preview",
    "agent-harness": "preview",
    "architecture": "preview",
    "bridges": "preview",
    "bytecode": "preview",
    "contract": "preview",
    "decision-log": "preview",
    "decisions": "preview",
    "evolve": "preview",
    "extension": "preview",
    "hints": "preview",
    "learn": "preview",
    "mutation": "preview",
    "oc-new": "preview",
    "policy": "preview",
    "preset": "preview",
    "profile": "preview",
    "review": "preview",
    "routes": "preview",
    "sdd": "preview",
    "simulate": "preview",
    "stack": "preview",
    "storage": "preview",
    "studio": "preview",
    "telemetry": "preview",
    # --- internal: dev/debug/legacy plumbing ---
    "approvals": "internal",
    "ask": "internal",
    "cache": "internal",
    "checkpoint": "internal",
    "command": "internal",
    "eval": "internal",
    "git": "internal",
    "inspect": "internal",
    "instructions": "internal",
    "onboard": "internal",
    "org": "internal",
    "playbooks": "internal",
    "provider": "internal",
    "quality": "internal",
    "release": "internal",
    "report": "internal",
    "trace": "internal",
    "watch": "internal",
    "workflows": "internal",
}


def maturity_for(command: str) -> Maturity:
    """Maturity for *command*; unknown commands default to ``preview``."""
    return COMMAND_MATURITY.get(command, "preview")
