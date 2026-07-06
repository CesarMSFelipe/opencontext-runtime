"""Built-in configuration profiles (PR-013, SPEC-CLI-013-02).

Named *configuration* profiles — ``balanced`` (default), ``low-cost``,
``enterprise``, ``research`` and ``performance`` — each a partial-config overlay
applied as the second layer of the seven-level resolver
(``config_resolver.resolve``). They set security/policy/provider/harness/
runtime-intelligence defaults appropriate to a posture. Three runtime-mode
profiles (plan §6) complete the set: ``ci`` (non-interactive, JSON-first),
``local`` (interactive, TUI on) and ``agent`` (approval-gated writes, bounded
context budget).

These are DISTINCT from the per-phase model-assignment profiles in
``sdd_profiles.py`` (``default``/``cheap``/``hybrid``/``premium``): config
profiles choose *governance and routing defaults*, model profiles choose *which
model runs each SDD phase*. ``profile list``/``profile explain`` surface both
families as labelled sections.

Each overlay touches only keys that already exist on :class:`OpenContextConfig`
so the merged result still validates under ``extra="forbid"``.
"""

from __future__ import annotations

from typing import Any

# The default config profile when none is selected (book §6/§7).
DEFAULT_PROFILE = "balanced"

# name -> (one-line description, overlay dict). Overlays are partial configs that
# ``_deep_merge`` layers over the built-in defaults.
BUILTIN_PROFILES: dict[str, dict[str, Any]] = {
    "balanced": {
        "description": (
            "Sensible defaults for everyday local development: private-project "
            "security, balanced policy, balanced provider routing, no forced "
            "approval, intelligence advisory-off."
        ),
        "overlay": {
            "security": {"mode": "private_project", "fail_closed": True},
            "policy": {"preset": "balanced", "command_enforcement": True},
            "providers": {"strategy": "balanced"},
            "harness": {"approval_required_for_writes": False, "tdd_mode": "ask"},
            "runtime_intelligence_enabled": False,
        },
    },
    "low-cost": {
        "description": (
            "Minimise spend: cheapest provider routing and a frugal posture. "
            "Good for large batch or budget-constrained runs."
        ),
        "overlay": {
            "security": {"mode": "private_project"},
            "policy": {"preset": "balanced"},
            "providers": {"strategy": "cheapest", "fallback": True},
            "harness": {"approval_required_for_writes": False},
            "runtime_intelligence_enabled": False,
        },
    },
    "enterprise": {
        "description": (
            "Strict governance for shared/regulated codebases: enterprise "
            "security, restricted policy with command enforcement, approval "
            "required before any write, strict TDD, and observability on."
        ),
        "overlay": {
            "security": {
                "mode": "enterprise",
                "fail_closed": True,
                "external_providers_enabled": False,
            },
            "policy": {"preset": "restricted", "command_enforcement": True, "engine_enabled": True},
            "providers": {"strategy": "enterprise", "fallback": True},
            "harness": {"approval_required_for_writes": True, "tdd_mode": "strict"},
            "runtime_intelligence_enabled": True,
        },
    },
    "research": {
        "description": (
            "Exploration-first: highest-quality provider routing and Runtime "
            "Intelligence on for cost/confidence/simulation insight. No forced "
            "approval so iteration stays fast."
        ),
        "overlay": {
            "security": {"mode": "private_project"},
            "policy": {"preset": "balanced"},
            "providers": {"strategy": "highest_quality"},
            "harness": {"approval_required_for_writes": False, "tdd_mode": "ask"},
            "runtime_intelligence_enabled": True,
        },
    },
    "performance": {
        "description": (
            "Optimise for latency/throughput: fastest provider routing, balanced "
            "policy, intelligence off to keep the loop lean."
        ),
        "overlay": {
            "security": {"mode": "private_project"},
            "policy": {"preset": "balanced"},
            "providers": {"strategy": "fastest", "fallback": True},
            "harness": {"approval_required_for_writes": False},
            "runtime_intelligence_enabled": False,
        },
    },
    # Runtime-mode profiles (plan §6): posture for WHERE the CLI runs rather
    # than governance strictness. They map onto existing config fields only.
    "ci": {
        "description": (
            "Non-interactive CI runs: no prompts, no TUI, machine-readable JSON output by default."
        ),
        "overlay": {
            "interface": {"interactive": False, "tui": False, "json_default": True},
        },
    },
    "local": {
        "description": "Interactive local development: prompts and TUI screens enabled.",
        "overlay": {
            "interface": {"interactive": True, "tui": True},
        },
    },
    "agent": {
        "description": (
            "Agent-driven runs: every write requires approval and the context "
            "budget is bounded to 24000 tokens."
        ),
        "overlay": {
            "harness": {"approval_required_for_writes": True},
            "context": {"max_input_tokens": 24000},
        },
    },
}


def profile_names() -> list[str]:
    """Return the built-in profile names (``balanced`` first)."""
    names = list(BUILTIN_PROFILES)
    names.sort(key=lambda n: (n != DEFAULT_PROFILE, n))
    return names


def get_profile(name: str) -> dict[str, Any]:
    """Return the overlay dict for *name*.

    Raises ``KeyError`` for an unknown profile so callers can surface an
    actionable error (``config_doctor`` / the resolver do this).
    """
    if name not in BUILTIN_PROFILES:
        raise KeyError(name)
    overlay = BUILTIN_PROFILES[name]["overlay"]
    # Return a deep-ish copy so callers can't mutate the module-level table.
    return {k: dict(v) if isinstance(v, dict) else v for k, v in overlay.items()}


def describe(name: str) -> str:
    """Return the one-line description for *name* (empty string if unknown)."""
    entry = BUILTIN_PROFILES.get(name)
    return str(entry["description"]) if entry else ""


def list_profiles() -> list[dict[str, Any]]:
    """Return ``[{name, description, default}]`` for every built-in profile."""
    return [
        {
            "name": name,
            "description": describe(name),
            "default": name == DEFAULT_PROFILE,
        }
        for name in profile_names()
    ]
