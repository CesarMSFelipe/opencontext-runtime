"""Orphan check — release cannot ship with orphaned or proposed-status capabilities.

The capability registry is the single source of truth for which v2
modules ship in a release. Two failure modes block the verdict:

1. **Orphan** — a capability id referenced by the SPEC, the
   architecture coverage report, or any testsuite but *not* declared
   in :data:`opencontext_core.capabilities.registry.REGISTERED_V2_CAPABILITIES`.
2. **Proposed** — a declared capability whose status is ``"proposed"``
   (or another non-release status). Only ``"stable"`` and
   ``"deprecated"`` are release-managed states.

The check is pure-data; it takes the declared and referenced sets as
inputs and returns a list of :class:`OrphanCapability` records the
gate runner inspects.
"""

from __future__ import annotations

from dataclasses import dataclass

# Release-managed statuses — capabilities in these states ship.
RELEASE_STATUSES: frozenset[str] = frozenset({"stable", "deprecated"})

# Statuses that block the release.
ORPHAN_STATUSES: frozenset[str] = frozenset({"proposed", "draft", "experimental", "unknown", ""})


@dataclass(frozen=True)
class OrphanCapability:
    """A capability that blocks the release verdict."""

    capability_id: str
    reason: str  # "orphan" or "proposed" / "draft" / etc.
    blocks_release: bool = True


def check_orphans(*, declared: set[str], referenced: set[str]) -> list[OrphanCapability]:
    """Return one :class:`OrphanCapability` per referenced-but-not-declared id."""
    return [
        OrphanCapability(capability_id=cid, reason="orphan")
        for cid in sorted(referenced - declared)
    ]


def check_proposed_status(statuses: dict[str, str]) -> list[str]:
    """Return the ids whose status is not in :data:`RELEASE_STATUSES`."""
    return sorted(cid for cid, status in statuses.items() if status not in RELEASE_STATUSES)
