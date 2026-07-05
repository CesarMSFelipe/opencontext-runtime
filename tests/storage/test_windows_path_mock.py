"""Mock test: Windows LOCALAPPDATA path resolution.

Spec scenario: "mode=user, Windows — LOCALAPPDATA used"
  GIVEN the runtime is on Windows and storage.mode = user
  WHEN resolve_storage_path is called
  THEN it returns a path rooted under LOCALAPPDATA/opencontext/projects/<id>

Because we run on Linux/macOS, we monkeypatch platformdirs.user_state_path
to simulate the Windows value without changing the resolver logic at all.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from opencontext_core.paths import StorageMode, project_id, resolve_storage_path


def test_resolve_storage_windows_mock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """resolver returns a path under the simulated Windows LOCALAPPDATA dir."""
    # Wipe XDG_STATE_HOME so the platformdirs fallback wins (the resolver
    # honors XDG_STATE_HOME cross-platform, but this test is exercising the
    # Windows platformdirs code path specifically).
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    fake_localappdata = tmp_path / "AppData" / "Local" / "opencontext"

    with patch(
        "opencontext_core.paths.platformdirs.user_state_path",
        return_value=fake_localappdata,
    ):
        path = resolve_storage_path(tmp_path, StorageMode.user)

    expected_prefix = fake_localappdata / "projects" / project_id(tmp_path)
    assert path == expected_prefix, f"Expected {expected_prefix}, got {path}"


def test_resolve_storage_windows_mock_different_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Different project roots produce different paths even under mocked Windows dir."""
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    fake_localappdata = tmp_path / "AppData" / "Local" / "opencontext"

    root_a = tmp_path / "project_a"
    root_a.mkdir()
    root_b = tmp_path / "project_b"
    root_b.mkdir()

    with patch(
        "opencontext_core.paths.platformdirs.user_state_path",
        return_value=fake_localappdata,
    ):
        path_a = resolve_storage_path(root_a, StorageMode.user)
        path_b = resolve_storage_path(root_b, StorageMode.user)

    assert path_a != path_b, "Different roots must produce different storage paths"
    assert str(fake_localappdata) in str(path_a)
    assert str(fake_localappdata) in str(path_b)
