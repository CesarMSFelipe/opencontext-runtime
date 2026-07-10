"""SDD workflow graph tables for the full SDD lifecycle.

Declares the module-level source-of-truth data for the nine phases of
Spec-Driven Development
(explore -> propose -> spec -> design -> tasks -> apply -> verify -> review ->
archive) plus the workflow tracks that select subsets of it.

The legacy ``SDDOrchestrator`` class was removed for the 2.0 cut (it had no live
readers — the live SDD flow runs through ``opencontext_core.harness``). These
tables and helpers remain the shared DAG declaration consumed by the harness
runner and ``explain``.
"""

from __future__ import annotations

PHASE_ORDER = [
    "explore",
    "propose",
    "spec",
    "design",
    "tasks",
    "apply",
    "verify",
    "review",
    "archive",
]

# Phase dependencies: which phases must complete before this one
PHASE_DEPENDENCIES: dict[str, list[str]] = {
    "explore": [],
    "propose": ["explore"],
    "spec": ["propose"],
    "design": ["propose"],
    "tasks": ["spec", "design"],
    "apply": ["tasks"],
    "verify": ["apply"],
    "review": ["verify"],
    "archive": ["review"],
}

# Workflow tracks: each track defines its own phase order and dependencies
# DEPRECATED(2.0): legacy workflow-track declaration; superseded by the PR-003
# WorkflowRegistry/builtins. Still consumed by the HarnessRunner DAG + explain.py while the
# runtime.registry_enabled rollback exists; remove when registry-driven scheduling replaces
# the legacy DAG (milestone-C).
WORKFLOW_TRACKS: dict[str, dict[str, object]] = {
    "quick": {
        "phases": ["explore", "apply", "verify"],
        "deps": {
            "explore": [],
            "apply": ["explore"],
            "verify": ["apply"],
        },
    },
    "standard": {
        # propose is required: SpecPhase/DesignPhase read proposal.json, which only
        # ProposePhase writes. Omitting it made spec+design fail their preconditions
        # (and never reach the executor, so per-phase model routing never fired).
        "phases": ["explore", "propose", "spec", "design", "apply", "verify"],
        "deps": {
            "explore": [],
            "propose": ["explore"],
            "spec": ["propose"],
            "design": ["propose"],
            "apply": ["spec", "design"],
            "verify": ["apply"],
        },
    },
    "full": {
        "phases": PHASE_ORDER,
        "deps": PHASE_DEPENDENCIES,
    },
    "sdd": {
        "phases": PHASE_ORDER,
        "deps": PHASE_DEPENDENCIES,
    },
    "full+judgment": {
        "phases": [*PHASE_ORDER, "judgment"],
        "deps": {**PHASE_DEPENDENCIES, "judgment": ["verify"]},
    },
    "full+gga": {
        "phases": [*PHASE_ORDER, "gga"],
        "deps": {**PHASE_DEPENDENCIES, "gga": ["verify"]},
    },
    "full+quality": {
        "phases": [*PHASE_ORDER, "gga", "judgment"],
        "deps": {**PHASE_DEPENDENCIES, "gga": ["verify"], "judgment": ["gga"]},
    },
}


def phase_required_harnesses(phase: str) -> list[str]:
    """Return the first-class ``required_harnesses`` declared for ``phase``.

    Sourced from the declarative ``OC_NEW_FLOW`` (spec PR-004 REQ-05). Imported
    lazily so this module's import graph is unchanged. Unknown phases yield ``[]``.
    """
    from opencontext_core.oc_new.flow import OC_NEW_FLOW

    for phase_def in OC_NEW_FLOW:
        if phase_def.name == phase:
            return list(phase_def.required_harnesses)
    return []


def resolve_phase_harness_modes(phase: str, profile: str | None = None) -> dict[str, str]:
    """Resolve each of ``phase``'s required harnesses to its effective mode.

    Consumes the PR-006 SDD harness matrix (``harness/matrix.py``) **read-only**
    via :func:`resolve_harness_mode` — strictness is profile-driven, not
    hardcoded here (REG-CONV). Returns a ``{harness_id: mode}`` digest a phase
    can attach to its receipt or use to decide blocking. Best-effort: an unknown
    harness resolves to the matrix's ``"warn"`` fallback. This module never edits
    the matrix; it only reads it.
    """
    from opencontext_core.harness.matrix import resolve_harness_mode

    return {h: resolve_harness_mode(h, profile) for h in phase_required_harnesses(phase)}


def sdd_definition_source() -> tuple[list[str], dict[str, list[str]], dict[str, str]]:
    """Return the SDD graph's source-of-truth data for the built-in definition.

    Exposes ``(PHASE_ORDER, PHASE_DEPENDENCIES, PHASE_PERSONAS)`` so the PR-003
    workflow registry's parity check can assert that ``builtins/sdd.yaml`` never
    drifts from the live scheduler graph (spec SDD1). No behavior change — this is a
    read-only accessor over existing module data. ``PHASE_PERSONAS`` is imported
    lazily to keep this module's import graph unchanged.
    """
    from opencontext_core.personas import PHASE_PERSONAS

    return list(PHASE_ORDER), dict(PHASE_DEPENDENCIES), dict(PHASE_PERSONAS)
