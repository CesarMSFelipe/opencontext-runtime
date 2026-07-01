"""SDD overlay JSON — per-phase sub-agent overlay for multi-agent orchestration.

Per openspec/changes/agentic-parity-engram-gentle/design.md §Orchestrator:

* ``sdd_overlay_multi`` — the canonical overlay dict mapping each SDD phase
  to its dedicated sub-agent, with ``chained_pr`` bound by registry name.

LB 2026 — SDD orchestrator overlay.
"""

from __future__ import annotations

from typing import Any

# ── Phase-to-agent overlay ──────────────────────────────────────────────────
# Maps each SDD phase to a sub-agent name. The orchestrator reads this
# overlay to spawn the right sub-agent for each phase.

SDD_OVERLAY_MULTI: dict[str, Any] = {
    "version": "1.0",
    "description": (
        "SDD multi-agent overlay: one sub-agent per phase. The orchestrator "
        "spawns the matching agent from this table and passes the phase prompt."
    ),
    "agents": {
        "explore": {"skill": "sdd-explore", "model": None},
        "propose": {"skill": "sdd-propose", "model": None},
        "spec": {"skill": "sdd-spec", "model": None},
        "design": {"skill": "sdd-design", "model": None},
        "tasks": {"skill": "sdd-tasks", "model": None},
        "apply": {"skill": "sdd-apply", "model": None},
        "verify": {"skill": "sdd-verify", "model": None},
        "archive": {"skill": "sdd-archive", "model": None},
    },
    "chained_pr": {
        "registry_name": "chained-pr",
        "description": (
            "Split oversized changes into chained PRs that protect review focus. "
            "Bound by registry name — the orchestrator resolves the SKILL.md path "
            "from the skill registry and loads it before planning or creating PRs."
        ),
    },
    "onboard": {
        "skill": "sdd-onboard",
        "description": "Walk users through the SDD workflow on the real codebase.",
    },
}


def get_overlay() -> dict[str, Any]:
    """Return the full SDD multi-agent overlay."""
    return SDD_OVERLAY_MULTI


def get_agent_for_phase(phase: str) -> str | None:
    """Return the sub-agent skill name for the given phase, or None."""
    agent = SDD_OVERLAY_MULTI.get("agents", {}).get(phase)
    return agent["skill"] if agent else None


def get_phase_list() -> list[str]:
    """Return the ordered list of SDD phase names."""
    return list(SDD_OVERLAY_MULTI.get("agents", {}).keys())


__all__ = [
    "SDD_OVERLAY_MULTI",
    "get_agent_for_phase",
    "get_overlay",
    "get_phase_list",
]
