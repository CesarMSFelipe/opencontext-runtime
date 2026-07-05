"""Per-profile SDD overlay — model assignments per orchestrator profile.

Per openspec/changes/agentic-parity-engram-gentle/design.md §Orchestrator:

* ``profiles`` — dict mapping profile names (``solo-compact``,
  ``opencontext``, ``subagent-native``, ``multi-phase``) to their
  per-phase model overrides.

LB 2026 — SDD profile overlay.
"""

from __future__ import annotations

from typing import Any

PROFILES: dict[str, dict[str, Any]] = {
    "default": {
        "description": "Default model assignments (no overrides).",
        "overrides": {},
    },
    "solo-compact": {
        "description": (
            "Solo-compact profile: single-agent execution with compact context "
            "packs. No model overrides — uses the host LLM for every phase."
        ),
        "overrides": {},
    },
    "opencontext": {
        "description": (
            "OpenContext orchestrator profile: dedicated sub-agents for "
            "high-risk phases. No model overrides by default."
        ),
        "overrides": {},
    },
    "subagent-native": {
        "description": (
            "Subagent-native profile: delegates to native sub-agents per phase. No model overrides."
        ),
        "overrides": {},
    },
    "multi-phase": {
        "description": (
            "Multi-phase profile: phases delegate to sub-agents with opinionated model assignments."
        ),
        "overrides": {
            "design": {"model": None},
            "apply": {"model": None},
            "verify": {"model": None},
        },
    },
}


def get_profile(name: str = "default") -> dict[str, Any]:
    """Return the profile config by name, or the default profile."""
    return PROFILES.get(name, PROFILES["default"])


def list_profiles() -> list[str]:
    """Return available profile names."""
    return list(PROFILES.keys())


__all__ = ["PROFILES", "get_profile", "list_profiles"]
