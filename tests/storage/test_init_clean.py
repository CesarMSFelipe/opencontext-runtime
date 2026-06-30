"""Integration test: opencontext init in user mode creates NO in-repo dirs.

Spec scenario: "Fresh init, mode=user — no repo dirs created"
  GIVEN a clean project repo and storage.mode = user
  WHEN the runtime initialises
  THEN no .storage/, .opencontext/, or .atl/ dirs exist in the repo
  AND storage IS created under XDG_STATE_HOME
"""

from __future__ import annotations

import yaml
from pathlib import Path

import pytest

from opencontext_core.config import OpenContextConfig, StorageConfig, default_config_data
from opencontext_core.paths import StorageMode, is_owned
from opencontext_core.runtime import OpenContextRuntime


def _make_config(project_root: Path, mode: StorageMode) -> OpenContextConfig:
    """Build a minimal OpenContextConfig for the given project root and mode."""
    data = default_config_data()
    data["project_index"]["root"] = str(project_root)
    data["project"]["name"] = "test-project"
    return OpenContextConfig.model_validate(data)


def test_init_user_mode_no_repo_dirs(xdg_state_tmp: Path, tmp_path: Path) -> None:
    """Runtime in user mode must not create .storage/.opencontext/.atl in repo."""
    project_root = tmp_path / "my_project"
    project_root.mkdir()

    config = _make_config(project_root, StorageMode.user)
    # Ensure user mode is active (default, and OPENCONTEXT_STORAGE_MODE is unset
    # by the xdg_state_tmp fixture).
    assert config.storage.mode == StorageMode.user

    rt = OpenContextRuntime(config=config)

    # No in-repo dirs should have been created.
    assert not (project_root / ".storage").exists(), (
        ".storage/ was created in the repo under user mode"
    )
    assert not (project_root / ".opencontext").exists(), (
        ".opencontext/ was created in the repo under user mode"
    )
    assert not (project_root / ".atl").exists(), (
        ".atl/ was created in the repo under user mode"
    )


def test_init_user_mode_storage_under_xdg(xdg_state_tmp: Path, tmp_path: Path) -> None:
    """Runtime in user mode writes storage under XDG_STATE_HOME."""
    project_root = tmp_path / "my_project"
    project_root.mkdir()

    config = _make_config(project_root, StorageMode.user)
    rt = OpenContextRuntime(config=config)

    # storage_path should be under the redirected XDG_STATE_HOME.
    assert str(xdg_state_tmp) in str(rt.storage_path), (
        f"Expected storage under {xdg_state_tmp}, got {rt.storage_path}"
    )
    assert rt.storage_path.exists()


def test_init_user_mode_manifest_written(xdg_state_tmp: Path, tmp_path: Path) -> None:
    """Runtime in user mode writes oc-manifest.json in the storage dir."""
    project_root = tmp_path / "my_project"
    project_root.mkdir()

    config = _make_config(project_root, StorageMode.user)
    rt = OpenContextRuntime(config=config)

    assert is_owned(rt.storage_path), (
        f"No valid manifest in {rt.storage_path}"
    )
