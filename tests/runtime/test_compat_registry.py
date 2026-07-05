"""Commit-006: compat registry carries the 5 v2 flags (amendment A2).

The 5 flags (``rt-spine``, ``mcp-runtime``, ``rt-budget``, ``skills-v2``,
``studio-control-plane``) are registered on the seeded
:class:`~opencontext_core.compat.migration.MigrationLedger` -- one per
v2 subsystem commit. Default state is ``legacy`` (i.e. ``False`` from the
consumer's perspective); migration happens via an accepted flip bundle.

The flag-based lookups live alongside the existing module-based
``is_migrated`` so CLI/MCP/TUI migrations can write
``compat.is_migrated_flag("rt-spine")`` instead of fishing for module paths.
"""

from __future__ import annotations

import pytest

from opencontext_core.compat.migration import (
    MIGRATION_LEDGER,
    MigrationState,
    is_migrated_flag,
)

# The 2 v2 subsystem flags still in legacy state.
# ``studio-control-plane`` was flipped to migrated at commit-013m (12-screen
# TUI live + v2 FastAPI surface); it is no longer in the pending set.
# ``rt-spine`` and ``mcp-runtime`` were flipped to migrated at C15 — parity
# suite tests/release/test_runtime_spine_parity.py + flip bundles
# tests/compat/flip_baseline/{rt_spine,mcp_runtime}.json.
V2_FLAGS = (
    "rt-budget",
    "skills-v2",
)


@pytest.mark.parametrize("flag", V2_FLAGS)
def test_all_v2_flags_default_false(flag: str) -> None:
    """Every v2 flag defaults to the legacy (``False``) state.

    Amendment A2: subsystems move forward via an accepted flip bundle, never
    by flipping the default. A ``True`` default would short-circuit the
    migration evidence.
    """
    assert is_migrated_flag(flag) is False, (
        f"flag {flag!r} must default to legacy (False); "
        "migrate via an accepted flip bundle, not a default flip"
    )


@pytest.mark.parametrize("flag", V2_FLAGS)
def test_all_v2_flags_are_registered_in_ledger(flag: str) -> None:
    """Every v2 flag maps to a registered ModuleMigration in the ledger.

    The ledger stores the dotted ``runtime.<flag>`` form; we match both
    forms (bare + dotted) so the consumer-facing API stays ``rt-spine`` and
    the internal flag catalog stays consistent.
    """
    dotted = f"runtime.{flag}"
    matches = [m for m in MIGRATION_LEDGER.modules if m.flag in {flag, dotted}]
    assert matches, f"no MIGRATION_LEDGER entry with flag={flag!r}"
    entry = matches[0]
    assert entry.state is MigrationState.legacy, (
        f"flag {flag!r} must be in legacy state (got {entry.state.value})"
    )
    assert entry.superseded_by is not None
    assert entry.removal_milestone is not None


def test_is_migrated_flag_returns_false_for_unknown_flag() -> None:
    """An unregistered flag must NOT silently return True."""
    assert is_migrated_flag("not-a-real-flag") is False
