"""Unit tests for opencontext_core.paths.

All tests use the ``xdg_state_tmp`` fixture (defined in tests/conftest.py) to
redirect XDG_STATE_HOME to a temporary directory so no real user state is
touched during the test run.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from opencontext_core.paths import (
    LegacyState,
    StorageMode,
    detect_legacy,
    is_owned,
    project_id,
    read_manifest,
    resolve_storage_path,
    resolve_workspace_path,
    write_manifest,
)


# ---------------------------------------------------------------------------
# project_id
# ---------------------------------------------------------------------------


def test_project_id_stable(tmp_path: Path) -> None:
    """Same root always returns the same project-id."""
    assert project_id(tmp_path) == project_id(tmp_path)


def test_project_id_different_roots(tmp_path: Path) -> None:
    """Different roots return different project-ids."""
    root_a = tmp_path / "a"
    root_a.mkdir()
    root_b = tmp_path / "b"
    root_b.mkdir()
    assert project_id(root_a) != project_id(root_b)


def test_project_id_is_12_chars(tmp_path: Path) -> None:
    """project_id always returns exactly 12 hex characters."""
    pid = project_id(tmp_path)
    assert len(pid) == 12
    assert all(c in "0123456789abcdef" for c in pid)


# ---------------------------------------------------------------------------
# resolve_storage_path
# ---------------------------------------------------------------------------


def test_resolve_storage_user_mode(xdg_state_tmp: Path, tmp_path: Path) -> None:
    """User mode returns a path under XDG_STATE_HOME / opencontext / projects."""
    path = resolve_storage_path(tmp_path, StorageMode.user)
    assert str(xdg_state_tmp) in str(path), (
        f"Expected path under {xdg_state_tmp}, got {path}"
    )
    assert "opencontext" in str(path)
    assert "projects" in str(path)
    assert project_id(tmp_path) in str(path)


def test_resolve_storage_local_mode(tmp_path: Path) -> None:
    """Local mode returns <root>/.storage/opencontext."""
    path = resolve_storage_path(tmp_path, StorageMode.local)
    assert path == tmp_path.resolve() / ".storage" / "opencontext"


def test_resolve_storage_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, xdg_state_tmp: Path
) -> None:
    """OPENCONTEXT_STORAGE_MODE=local overrides mode=user."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    path = resolve_storage_path(tmp_path, StorageMode.user)
    assert path == tmp_path.resolve() / ".storage" / "opencontext"


def test_resolve_storage_custom_path(tmp_path: Path) -> None:
    """A custom path overrides both modes."""
    custom = str(tmp_path / "my_custom_store")
    path = resolve_storage_path(tmp_path, StorageMode.user, custom=custom)
    assert path == Path(custom)


# ---------------------------------------------------------------------------
# resolve_workspace_path
# ---------------------------------------------------------------------------


def test_resolve_workspace_user_mode(xdg_state_tmp: Path, tmp_path: Path) -> None:
    """User mode workspace is storage_path / workspace."""
    storage = resolve_storage_path(tmp_path, StorageMode.user)
    workspace = resolve_workspace_path(tmp_path, StorageMode.user)
    assert workspace == storage / "workspace"


def test_resolve_workspace_local_mode(tmp_path: Path) -> None:
    """Local mode workspace is <root>/.opencontext."""
    workspace = resolve_workspace_path(tmp_path, StorageMode.local)
    assert workspace == tmp_path.resolve() / ".opencontext"


# ---------------------------------------------------------------------------
# detect_legacy
# ---------------------------------------------------------------------------


def test_detect_legacy_none(tmp_path: Path) -> None:
    """Empty project root returns None (no legacy dirs)."""
    result = detect_legacy(tmp_path)
    assert result is None


def test_detect_legacy_storage(tmp_path: Path) -> None:
    """Existing .storage/opencontext is reported as LegacyState."""
    legacy_storage = tmp_path / ".storage" / "opencontext"
    legacy_storage.mkdir(parents=True)
    result = detect_legacy(tmp_path)
    assert result is not None
    assert isinstance(result, LegacyState)
    assert result.storage_path == legacy_storage
    assert result.workspace_path is None


def test_detect_legacy_workspace(tmp_path: Path) -> None:
    """Existing .opencontext is reported as LegacyState."""
    legacy_ws = tmp_path / ".opencontext"
    legacy_ws.mkdir()
    result = detect_legacy(tmp_path)
    assert result is not None
    assert result.workspace_path == legacy_ws
    assert result.storage_path is None


def test_detect_legacy_both(tmp_path: Path) -> None:
    """Both legacy dirs are detected simultaneously."""
    (tmp_path / ".storage" / "opencontext").mkdir(parents=True)
    (tmp_path / ".opencontext").mkdir()
    result = detect_legacy(tmp_path)
    assert result is not None
    assert result.storage_path is not None
    assert result.workspace_path is not None


# ---------------------------------------------------------------------------
# write_manifest / read_manifest round-trip
# ---------------------------------------------------------------------------


def test_manifest_roundtrip(tmp_path: Path) -> None:
    """write_manifest then read_manifest returns equivalent data."""
    state_dir = tmp_path / "state"
    write_manifest(state_dir, tmp_path, version="1.0.0")
    data = read_manifest(state_dir)
    assert data is not None
    assert data["app"] == "opencontext"
    assert data["project_root"] == str(tmp_path.resolve())
    assert data["project_id"] == project_id(tmp_path)
    assert data["version"] == "1.0.0"
    assert "created_at" in data


def test_read_manifest_missing(tmp_path: Path) -> None:
    """read_manifest returns None when no manifest file exists."""
    assert read_manifest(tmp_path) is None


def test_read_manifest_invalid_json(tmp_path: Path) -> None:
    """read_manifest returns None when the manifest file contains invalid JSON."""
    manifest_file = tmp_path / "oc-manifest.json"
    manifest_file.write_text("{not valid json}", encoding="utf-8")
    assert read_manifest(tmp_path) is None


# ---------------------------------------------------------------------------
# is_owned
# ---------------------------------------------------------------------------


def test_is_owned_true(tmp_path: Path) -> None:
    """Dir with a valid OC manifest is owned."""
    write_manifest(tmp_path, tmp_path, version="1.0.0")
    assert is_owned(tmp_path) is True


def test_is_owned_false_no_manifest(tmp_path: Path) -> None:
    """Dir without a manifest file is not owned."""
    assert is_owned(tmp_path) is False


def test_is_owned_false_wrong_app(tmp_path: Path) -> None:
    """Dir whose manifest has app != 'opencontext' is not owned."""
    manifest_file = tmp_path / "oc-manifest.json"
    manifest_file.write_text(
        json.dumps({"app": "other-tool", "project_root": str(tmp_path)}),
        encoding="utf-8",
    )
    assert is_owned(tmp_path) is False
