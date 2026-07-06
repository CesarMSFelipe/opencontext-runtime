"""Canonical memory type taxonomy (MEMORY_CONTRACT `## Types`).

MEM-TYPES: the v2 observation type vocabulary is pinned to the contract's
canonical set; documented plan-level names normalize onto it, and legacy
free-form types keep working (additive behavior, no rejection).
"""

from __future__ import annotations

from pathlib import Path

from opencontext_memory import (
    CANONICAL_MEMORY_TYPES,
    MEMORY_TYPE_ALIASES,
    MemoryStore,
    mem_save,
    normalize_memory_type,
)
from opencontext_memory.tools.mem_get_observation import mem_get_observation


def _make_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore.open(tmp_path / "memory.sqlite3")


def _save(store: MemoryStore, *, type: str, content: str):
    return mem_save(
        store,
        session_id="s-1",
        project="proj",
        title="Typed note",
        content=content,
        type=type,
    )


def test_canonical_type_set_matches_memory_contract() -> None:
    """MEM-TYPES: the canonical type set is exactly MEMORY_CONTRACT's eight types."""
    assert CANONICAL_MEMORY_TYPES == frozenset(
        {
            "fact",
            "decision",
            "preference",
            "constraint",
            "pattern",
            "failure",
            "solution",
            "project_context",
        }
    )


def test_plan_aliases_normalize_to_canonical_types() -> None:
    """MEM-TYPES: plan-level names map onto canonical contract types."""
    assert MEMORY_TYPE_ALIASES == {
        "project_rule": "constraint",
        "learned_pattern": "pattern",
        "error_resolution": "solution",
    }
    for alias, canonical in MEMORY_TYPE_ALIASES.items():
        assert normalize_memory_type(alias) == canonical
        assert canonical in CANONICAL_MEMORY_TYPES


def test_normalize_keeps_canonical_and_free_form_types() -> None:
    """MEM-TYPES: canonical types pass through; unknown types stay verbatim."""
    for canonical in CANONICAL_MEMORY_TYPES:
        assert normalize_memory_type(canonical) == canonical
    # Legacy/free-form vocabulary keeps working — validation is additive.
    for legacy in ("manual", "bugfix", "discovery", "summary"):
        assert normalize_memory_type(legacy) == legacy


def test_save_normalizes_alias_types_into_the_store(tmp_path: Path) -> None:
    """MEM-TYPES: `mem_save` stores the canonical type for a plan-level alias."""
    store = _make_store(tmp_path)
    receipt = _save(store, type="project_rule", content="Deploys go through the release branch.")
    row = mem_get_observation(store, observation_id=receipt.receipt.id)
    assert row["type"] == "constraint"
    assert receipt.receipt.type == "constraint"


def test_save_preserves_canonical_and_legacy_types(tmp_path: Path) -> None:
    """MEM-TYPES: canonical and legacy free-form types round-trip unchanged."""
    store = _make_store(tmp_path)
    canonical = _save(store, type="preference", content="Reviewer prefers small diffs.")
    assert mem_get_observation(store, observation_id=canonical.receipt.id)["type"] == "preference"
    legacy = _save(store, type="bugfix", content="Fixed the N+1 in the user list.")
    assert mem_get_observation(store, observation_id=legacy.receipt.id)["type"] == "bugfix"
