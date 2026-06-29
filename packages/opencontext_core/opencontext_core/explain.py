"""Shared workflow/profile explanation logic (PR-013, SPEC-CLI-013-10).

One source of truth behind both the CLI (``workflow explain`` / ``profile
explain`` / ``profile list``) and the MCP meta tools
(``opencontext_workflow_list/explain``, ``opencontext_profile_list/explain``).
Interface-neutral: returns plain dicts; each surface renders them.
"""

from __future__ import annotations

from typing import Any

from opencontext_core import config_profiles
from opencontext_core.sdd_profiles import SDDProfileManager

# Curated when / when-not / cost / outputs per known workflow. Phases and
# harnesses are sourced live from the harness track tables so they cannot drift.
_WORKFLOW_GUIDE: dict[str, dict[str, Any]] = {
    "sdd": {
        "when": "Broad, high-risk, or multi-file changes needing a spec/design trail.",
        "when_not": "Tiny localized fixes — prefer 'oc-flow' for speed.",
        "cost": "high",
        "risk": "low (gated, full evidence spine)",
        "outputs": ["proposal.md", "spec.md", "design.md", "tasks.md", "code edits", "receipt"],
    },
    "oc-flow": {
        "when": "Localized engineering tasks: a failing test, small bugfix, lint/type fix.",
        "when_not": "Large architectural changes — escalate to 'sdd'.",
        "cost": "low",
        "risk": "medium (fast lane, fewer gates)",
        "outputs": ["diagnosis", "code edits", "verification", "receipt"],
    },
    "standard": {
        "when": "Medium changes that want spec+design but not the full SDD trail.",
        "when_not": "Trivial fixes or sweeping refactors.",
        "cost": "medium",
        "risk": "low",
        "outputs": ["proposal", "spec", "design", "code edits"],
    },
    "quick": {
        "when": "Explore → apply → verify with no planning artifacts.",
        "when_not": "Anything needing review-ready specs.",
        "cost": "low",
        "risk": "medium",
        "outputs": ["code edits", "verification"],
    },
}


def _track_phases(workflow_id: str) -> list[str]:
    """Resolve a workflow's phase list from the harness track tables."""
    try:
        from opencontext_core.agents.sdd_orchestrator import WORKFLOW_TRACKS
        from opencontext_core.harness.runner import HarnessRunner

        track_name = HarnessRunner._WORKFLOW_TRACK_ALIASES.get(workflow_id, workflow_id)
        track = WORKFLOW_TRACKS.get(track_name)
        if track is None:
            return []
        phases = track.get("phases", [])
        return [str(p) for p in phases] if isinstance(phases, list) else []
    except Exception:
        return []


def _phase_harnesses(phases: list[str]) -> list[str]:
    harnesses: list[str] = []
    try:
        from opencontext_core.agents.sdd_orchestrator import phase_required_harnesses

        for phase in phases:
            for h in phase_required_harnesses(phase):
                if h not in harnesses:
                    harnesses.append(h)
    except Exception:
        pass
    return harnesses


def known_workflows() -> list[str]:
    names = list(_WORKFLOW_GUIDE)
    try:
        from opencontext_core.agents.sdd_orchestrator import WORKFLOW_TRACKS

        for name in WORKFLOW_TRACKS:
            if name not in names:
                names.append(name)
    except Exception:
        pass
    return names


def list_workflows(root: str = ".") -> list[dict[str, Any]]:
    """Return ``[{id, cost, when}]`` for every known workflow."""
    out: list[dict[str, Any]] = []
    for wid in known_workflows():
        guide = _WORKFLOW_GUIDE.get(wid, {})
        out.append(
            {
                "id": wid,
                "cost": guide.get("cost", "unknown"),
                "when": guide.get("when", ""),
            }
        )
    return out


def explain_workflow(workflow_id: str, root: str = ".") -> dict[str, Any]:
    """Describe a workflow: when/when-not/cost/risk/outputs/phases/harnesses."""
    phases = _track_phases(workflow_id)
    guide = _WORKFLOW_GUIDE.get(workflow_id)
    if guide is None and not phases:
        return {
            "error": f"unknown workflow: {workflow_id}",
            "next_action": "run 'opencontext workflow explain' with one of: "
            + ", ".join(known_workflows()),
        }
    guide = guide or {}
    return {
        "id": workflow_id,
        "when": guide.get("when", ""),
        "when_not": guide.get("when_not", ""),
        "cost": guide.get("cost", "unknown"),
        "risk": guide.get("risk", "unknown"),
        "outputs": guide.get("outputs", []),
        "phases": phases,
        "harnesses": _phase_harnesses(phases),
    }


def list_profiles_all() -> dict[str, Any]:
    """Return both profile families as labelled sections."""
    manager = SDDProfileManager()
    return {
        "config_profiles": config_profiles.list_profiles(),
        "model_profiles": manager.list_profiles(),
    }


def explain_profile(profile_id: str) -> dict[str, Any]:
    """Describe a config profile: workflow-defaults/security/budget/approvals/...

    Falls back to describing a model-assignment profile when *profile_id* names
    one of the ``sdd_profiles.py`` families instead.
    """
    if profile_id in config_profiles.BUILTIN_PROFILES:
        overlay = config_profiles.get_profile(profile_id)
        security = overlay.get("security", {})
        policy = overlay.get("policy", {})
        providers = overlay.get("providers", {})
        harness = overlay.get("harness", {})
        return {
            "id": profile_id,
            "family": "config",
            "description": config_profiles.describe(profile_id),
            "default": profile_id == config_profiles.DEFAULT_PROFILE,
            "security": security,
            "policy": policy,
            "providers": providers,
            "approvals": {
                "approval_required_for_writes": harness.get(
                    "approval_required_for_writes", False
                ),
                "tdd_mode": harness.get("tdd_mode", "ask"),
            },
            "observability": {
                "runtime_intelligence_enabled": overlay.get(
                    "runtime_intelligence_enabled", False
                )
            },
            "budget": {"provider_strategy": providers.get("strategy", "balanced")},
        }

    # Model-assignment profile fallback.
    manager = SDDProfileManager()
    model_profile = manager.get_profile(profile_id)
    if model_profile is not None:
        return {
            "id": profile_id,
            "family": "model",
            "description": model_profile.description,
            "model_assignments": model_profile.model_assignments,
        }

    return {
        "error": f"unknown profile: {profile_id}",
        "next_action": "run 'opencontext profile list' to see available profiles.",
    }
