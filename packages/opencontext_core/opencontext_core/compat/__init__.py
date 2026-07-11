"""Compatibility layer: Legacy <-> Runtime vNext migration governance (PR-000.0).

A single declared boundary that lets the legacy execution code coexist with the
Runtime vNext substrate while PR-001..017 land, so ``feat/agentic-engineering-runtime``
stays runnable as legacy is retired progressively. This package is governance data
plus thin seams -- it builds no vNext subsystem and is inert until an owning PR
lands an adapter body and flips its flag.

Contents:
  - ``migration``  -- ``MigrationState`` + seeded ``MIGRATION_LEDGER`` + ``is_migrated``
                      predicate (4 CL-006 conditions) + two-spine convergence record.
  - ``flags``      -- read-only catalog of the ``runtime.*`` dual-run flags (CL-005).
  - ``collisions`` -- the 4 name-collision resolution rules (CL-009).
  - ``parity``     -- the parity-gate helper guarding every flag flip (CL-012).
  - ``registry``   -- ``LegacyAdapter`` protocol + ``AdapterRegistry`` (CL-001..004).
  - ``seams``      -- the canonical HarnessApi seam + deferred Workflow/Provider/Context seams.

It also re-exports the Python-version compatibility helpers (``UTC``, ``StrEnum``)
that previously lived in the standalone ``compat.py`` module, folded in here so the
~40 existing ``from opencontext_core.compat import ...`` call-sites keep working.
"""

from __future__ import annotations

from datetime import timezone
from enum import StrEnum

from opencontext_core.compat.collisions import (
    COLLISION_REGISTRY,
    CollisionRule,
    NameCollision,
    collision,
)
from opencontext_core.compat.flags import FlagSpec, flag_catalog, flag_spec
from opencontext_core.compat.migration import (
    MIGRATION_LEDGER,
    TWO_SPINE_CONVERGENCE,
    MigrationLedger,
    MigrationState,
    ModuleMigration,
    TwoSpineDecision,
    direct_legacy_importers,
    is_migrated,
    is_migrated_flag,
)
from opencontext_core.compat.parity import (
    ParityGateError,
    ParityReport,
    assert_parity,
    check_parity,
)
from opencontext_core.compat.registry import AdapterRegistry, LegacyAdapter
from opencontext_core.compat.seams import (
    HarnessApiAdapter,
    LegacyContextAdapter,
    LegacyProviderAdapter,
    LegacyWorkflowAdapter,
)

# Python-version compatibility shim (folded from the former compat.py).
UTC = timezone.utc  # noqa: UP017


def coerce_yaml_off(value: object) -> object:
    """Map YAML's unquoted ``off`` (parsed as ``False``) back to the string "off".

    YAML's "Norway problem": an unquoted ``off`` parses as the boolean ``False``,
    so any config field whose ``Literal`` includes ``"off"`` fails validation when
    a user hand-writes ``field: off``. Coerce that one collision back to the
    string; genuine strings and every other value pass through untouched. Attach
    with ``field_validator("<field>", mode="before")`` on each such field.
    """
    return "off" if value is False else value


__all__ = [
    "COLLISION_REGISTRY",
    "MIGRATION_LEDGER",
    "TWO_SPINE_CONVERGENCE",
    "UTC",
    "AdapterRegistry",
    "CollisionRule",
    "FlagSpec",
    "HarnessApiAdapter",
    "LegacyAdapter",
    "LegacyContextAdapter",
    "LegacyProviderAdapter",
    "LegacyWorkflowAdapter",
    "MigrationLedger",
    "MigrationState",
    "ModuleMigration",
    "NameCollision",
    "ParityGateError",
    "ParityReport",
    "StrEnum",
    "TwoSpineDecision",
    "assert_parity",
    "check_parity",
    "coerce_yaml_off",
    "collision",
    "direct_legacy_importers",
    "flag_catalog",
    "flag_spec",
    "is_migrated",
    "is_migrated_flag",
]
