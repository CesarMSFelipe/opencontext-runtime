"""Compatibility alias table (spec WR2).

Maps each legacy workflow name to a canonical ``(workflow_id, profile)`` pair. This
is the registry-level adapter for the legacy ``HarnessRunner._WORKFLOW_TRACK_ALIASES``
table (pr-000-0 compatibility layer): the legacy names keep resolving, now onto a
single SDD ``WorkflowDefinition`` plus the profile that reproduces each name's
historical phase set, rather than four scattered tracks.
"""

from __future__ import annotations

# Legacy name -> (canonical workflow id, phase-subset profile). The profile name
# matches a phase-subset profile declared on the target definition, so the resolved
# phase order equals the legacy track's order (spec BAK1). The SDD-subset tracks
# (full/standard/quick/explore-only/apply-only) resolve onto the SDD definition; the
# quality tracks (full+judgment/full+gga/full+quality) add judgment/gga phases the
# SDD graph lacks and so resolve onto the derived ``sdd-quality`` definition. Every
# legacy track that the legacy HarnessRunner scheduled (WORKFLOW_TRACKS +
# explore-only/apply-only subsets) is mapped here, so registry resolution never
# falls back with a ``workflow.validation.failed`` event for a *known* track —
# that event stays reserved for genuinely unknown workflows (spec VDM-004).
WORKFLOW_ALIASES: dict[str, tuple[str, str]] = {
    "full": ("sdd", "full"),
    "standard": ("sdd", "standard"),
    "quick": ("sdd", "quick"),
    "sdd": ("sdd", "full"),
    "explore-only": ("sdd", "explore-only"),
    "apply-only": ("sdd", "apply-only"),
    "full+judgment": ("sdd-quality", "full+judgment"),
    "full+gga": ("sdd-quality", "full+gga"),
    "full+quality": ("sdd-quality", "full+quality"),
}


class UnknownWorkflowAlias(KeyError):
    """Raised when a legacy alias has no mapping."""


def resolve_alias(name: str) -> tuple[str, str]:
    """Return the ``(workflow_id, profile)`` for a legacy alias ``name``.

    Raises :class:`UnknownWorkflowAlias` when ``name`` is not a known alias.
    """
    try:
        return WORKFLOW_ALIASES[name]
    except KeyError as exc:
        raise UnknownWorkflowAlias(f"unknown workflow alias: {name!r}") from exc


def is_alias(name: str) -> bool:
    """Return True when ``name`` is a known legacy alias."""
    return name in WORKFLOW_ALIASES
