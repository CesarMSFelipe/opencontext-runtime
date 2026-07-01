"""Integration tests: runtime storage-mode behaviour.

Covers:
- user mode writes storage to XDG, not repo
- local mode writes to .storage/opencontext in repo
- manifest is written in user mode
- legacy in-repo state triggers a warning in user mode
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from opencontext_core.config import OpenContextConfig, StorageConfig, default_config_data
from opencontext_core.paths import StorageMode, is_owned
from opencontext_core.runtime import OpenContextRuntime


def _config(project_root: Path, mode: StorageMode | None = None) -> OpenContextConfig:
    """Build a minimal config for *project_root*, optionally fixing *mode*."""
    data = default_config_data()
    data["project_index"]["root"] = str(project_root)
    data["project"]["name"] = "test-project"
    cfg = OpenContextConfig.model_validate(data)
    if mode is not None:
        # Patch the storage config directly on the validated instance.
        object.__setattr__(cfg, "storage", StorageConfig(mode=mode))
    return cfg


def test_runtime_user_mode_storage_in_xdg(xdg_state_tmp: Path, tmp_path: Path) -> None:
    """In user mode, runtime.storage_path is under XDG_STATE_HOME."""
    project_root = tmp_path / "proj"
    project_root.mkdir()
    rt = OpenContextRuntime(config=_config(project_root, StorageMode.user))
    assert str(xdg_state_tmp) in str(rt.storage_path)
    assert not (project_root / ".storage").exists()


def test_runtime_local_mode_storage_in_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In local mode, runtime.storage_path is under <root>/.storage/opencontext."""
    monkeypatch.delenv("OPENCONTEXT_STORAGE_MODE", raising=False)
    project_root = tmp_path / "proj"
    project_root.mkdir()
    rt = OpenContextRuntime(config=_config(project_root, StorageMode.local))
    expected = project_root.resolve() / ".storage" / "opencontext"
    assert rt.storage_path == expected
    assert rt.storage_path.exists()


def test_runtime_manifest_written(xdg_state_tmp: Path, tmp_path: Path) -> None:
    """User mode runtime writes a valid oc-manifest.json into storage_path."""
    project_root = tmp_path / "proj"
    project_root.mkdir()
    rt = OpenContextRuntime(config=_config(project_root, StorageMode.user))
    assert is_owned(rt.storage_path), f"No manifest found at {rt.storage_path}"


def test_runtime_legacy_detected(xdg_state_tmp: Path, tmp_path: Path) -> None:
    """If legacy .storage/opencontext exists in repo, runtime emits a warning."""
    project_root = tmp_path / "proj"
    project_root.mkdir()
    # Seed a legacy in-repo storage dir.
    legacy_dir = project_root / ".storage" / "opencontext"
    legacy_dir.mkdir(parents=True)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        OpenContextRuntime(config=_config(project_root, StorageMode.user))

    legacy_warnings = [w for w in caught if "legacy local state detected" in str(w.message)]
    assert legacy_warnings, (
        "Expected 'legacy local state detected' warning but none was emitted. "
        f"Warnings captured: {[str(w.message) for w in caught]}"
    )
    # Legacy dir must NOT be deleted.
    assert legacy_dir.exists(), "Legacy dir was deleted — it must be preserved"
