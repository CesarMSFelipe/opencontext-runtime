"""Tests for OcNewStore."""

from __future__ import annotations

import pytest

from opencontext_core.oc_new.conductor import OcNewConductor
from opencontext_core.oc_new.store import OcNewStore


def test_store_save_and_load(tmp_path):
    conductor = OcNewConductor(tmp_path)
    state = conductor.start("Test task")
    run_id = state.identity.run_id

    store = OcNewStore(tmp_path)
    loaded = store.load(run_id)
    assert loaded.task == "Test task"
    assert loaded.identity.run_id == run_id


def test_store_load_missing(tmp_path):
    store = OcNewStore(tmp_path)
    with pytest.raises(FileNotFoundError):
        store.load("nonexistent-run-id")


def test_store_latest_returns_most_recent(tmp_path):
    conductor = OcNewConductor(tmp_path)
    conductor.start("First task")
    state2 = conductor.start("Second task")

    store = OcNewStore(tmp_path)
    latest = store.latest()
    assert latest is not None
    assert latest.identity.run_id == state2.identity.run_id


def test_store_latest_empty(tmp_path):
    store = OcNewStore(tmp_path)
    assert store.latest() is None


def test_store_list_runs(tmp_path):
    conductor = OcNewConductor(tmp_path)
    conductor.start("Task A")
    conductor.start("Task B")

    store = OcNewStore(tmp_path)
    runs = store.list_runs()
    assert len(runs) == 2
    tasks = {r.task for r in runs}
    assert tasks == {"Task A", "Task B"}
