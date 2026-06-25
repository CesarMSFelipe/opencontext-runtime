"""Tests for InstallState.files ledger and atomic _save_state."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from opencontext_core.install_manager import InstallState, InstallationManager


def test_install_state_files_default():
    state = InstallState()
    assert state.files == []


def test_backward_compat_no_files_key(tmp_path):
    """Old install-state.json without 'files' deserialises to files==[]."""
    state_path = tmp_path / "install-state.json"
    state_path.write_text(
        json.dumps({"version": "0.1.0", "agents": [], "components": []}), encoding="utf-8"
    )
    mgr = InstallationManager.__new__(InstallationManager)
    mgr.state_path = state_path
    loaded = mgr._load_state()
    assert loaded is not None
    assert loaded.files == []


def test_round_trip_with_files(tmp_path):
    """files list survives save → load cycle."""
    state_path = tmp_path / "install-state.json"
    mgr = InstallationManager.__new__(InstallationManager)
    mgr.state_path = state_path
    mgr._save_state(InstallState(files=["a/b.md", "c/d.md"]))
    loaded = mgr._load_state()
    assert loaded is not None
    assert loaded.files == ["a/b.md", "c/d.md"]


def test_atomic_save_no_tmp_remains(tmp_path):
    """Temp file is renamed to final path; no .tmp lingers after save."""
    state_path = tmp_path / "install-state.json"
    mgr = InstallationManager.__new__(InstallationManager)
    mgr.state_path = state_path
    mgr._save_state(InstallState(files=["x/y.md"]))
    assert state_path.exists()
    assert not state_path.with_suffix(".tmp").exists()


def test_atomic_save_uses_replace(tmp_path, monkeypatch):
    """_save_state calls os.replace (not write_text) for atomicity."""
    replaced: list[tuple[str, str]] = []
    real_replace = os.replace

    def _spy(src, dst):
        replaced.append((src, dst))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _spy)
    state_path = tmp_path / "install-state.json"
    mgr = InstallationManager.__new__(InstallationManager)
    mgr.state_path = state_path
    mgr._save_state(InstallState())
    assert len(replaced) == 1
    assert Path(replaced[0][1]) == state_path
