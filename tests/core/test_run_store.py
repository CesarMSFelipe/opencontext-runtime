"""Tests for RunStore."""

from __future__ import annotations

import json

import pytest

from opencontext_core.harness.run_store import RunStore


def test_store_creates_runs_dir(tmp_path):
    RunStore(tmp_path)
    assert (tmp_path / ".opencontext" / "runs").exists()


def test_register_and_artifact_path(tmp_path):
    store = RunStore(tmp_path)
    art_dir = tmp_path / "artifacts" / "run-001"
    store.register("run-001", art_dir)
    assert store.artifact_path("run-001", "spec.md") == art_dir / "spec.md"


def test_list_run_ids(tmp_path):
    store = RunStore(tmp_path)
    for rid in ["run-a", "run-b", "run-c"]:
        store.register(rid, tmp_path / rid)
    assert store.list_run_ids() == ["run-a", "run-b", "run-c"]


def test_exists_true_and_false(tmp_path):
    store = RunStore(tmp_path)
    store.register("run-x", tmp_path / "x")
    assert store.exists("run-x") is True
    assert store.exists("run-y") is False


def test_artifact_path_missing_raises(tmp_path):
    store = RunStore(tmp_path)
    with pytest.raises(KeyError):
        store.artifact_path("unknown-run", "file.txt")


def test_register_persists_across_instances(tmp_path):
    RunStore(tmp_path).register("run-persist", tmp_path / "persist")
    store2 = RunStore(tmp_path)
    assert store2.exists("run-persist")


def test_index_file_is_valid_json(tmp_path):
    store = RunStore(tmp_path)
    store.register("run-json", tmp_path / "json")
    index_file = tmp_path / ".opencontext" / "runs" / "index.json"
    assert index_file.exists()
    data = json.loads(index_file.read_text())
    assert isinstance(data, dict)
    assert "run-json" in data
