"""Compatibility alias table (spec WR2).

Maps each legacy workflow name to a canonical ``(workflow_id, profile)`` pair. This
is the registry-level adapter for the legacy ``HarnessRunner._WORKFLOW_TRACK_ALIASES``
table (pr-000-0 compatibility layer): the legacy names keep resolving, now onto a
single SDD ``WorkflowDefinition`` plus the profile that reproduces each name's
historical phase set, rather than four scattered tracks.
"""

from __future__ import annotations

# Legacy name -> (canonical workflow id, phase-subset profile). The profile name
# matches a phase-subset profile declared on the SDD definition (full/standard/quick),
# so the resolved phase order equals the legacy track's order (spec BAK1).
WORKFLOW_ALIASES: dict[str, tuple[str, str]] = {
    "full": ("sdd", "full"),
    "standard": ("sdd", "standard"),
    "quick": ("sdd", "quick"),
    "sdd": ("sdd", "full"),
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
