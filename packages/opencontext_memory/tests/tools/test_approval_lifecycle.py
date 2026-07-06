"""Approval lifecycle: proposed saves, search exclusion, approve / reject verbs.

MEMORY_CONTRACT states: `proposed` memories are not used in packs/runs unless
configuration explicitly allows it; `approve` maps proposed -> active (the
approved default) and `reject` discards the row so it is never retrieved.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from opencontext_memory import MemoryStore, mem_approve, mem_reject, mem_save, mem_search
from opencontext_memory.tools.mem_get_observation import MemoryNotFound, mem_get_observation


def _make_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore.open(tmp_path / "memory.sqlite3")


def _save(store: MemoryStore, *, proposed: bool = False, content: str = "users get 500 on POST"):
    return mem_save(
        store,
        session_id="s-1",
        project="proj",
        title="Login bug",
        content=content,
        type="bugfix",
        proposed=proposed,
    )


def test_default_save_lands_active(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    receipt = _save(store)
    row = mem_get_observation(store, observation_id=receipt.receipt.id)
    assert row["lifecycle_state"] == "active"


def test_proposed_save_lands_proposed(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    receipt = _save(store, proposed=True)
    row = mem_get_observation(store, observation_id=receipt.receipt.id)
    assert row["lifecycle_state"] == "proposed"


def test_search_excludes_proposed_by_default(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    receipt = _save(store, proposed=True)
    hits = mem_search(store, query="login bug", project="proj")
    assert all(h["id"] != receipt.receipt.id for h in hits)


def test_search_include_proposed_flag_surfaces_proposed(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    receipt = _save(store, proposed=True)
    hits = mem_search(store, query="login bug", project="proj", include_proposed=True)
    assert any(h["id"] == receipt.receipt.id for h in hits)


def test_approve_transitions_proposed_to_active(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    receipt = _save(store, proposed=True)
    result = mem_approve(store, observation_id=receipt.receipt.id)
    assert result["approved"] is True
    assert result["previous_state"] == "proposed"
    assert result["lifecycle_state"] == "active"
    hits = mem_search(store, query="login bug", project="proj")
    assert any(h["id"] == receipt.receipt.id for h in hits)


def test_reject_discards_the_row_for_good(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    receipt = _save(store, proposed=True)
    result = mem_reject(store, observation_id=receipt.receipt.id)
    assert result["rejected"] is True
    assert result["lifecycle_state"] == "rejected"
    with pytest.raises(MemoryNotFound):
        mem_get_observation(store, observation_id=receipt.receipt.id)
    hits = mem_search(store, query="login bug", project="proj", include_proposed=True)
    assert all(h["id"] != receipt.receipt.id for h in hits)


def test_approve_unknown_id_raises(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    with pytest.raises(LookupError):
        mem_approve(store, observation_id=999)


def test_reject_unknown_id_raises(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    with pytest.raises(LookupError):
        mem_reject(store, observation_id=999)
