"""Tests: manifest-gated uninstall behaviour.

Covers spec scenarios:
- "Uninstall — deletes only manifest-owned dirs"
- "Manifest mismatch aborts deletion"
- User-mode XDG state cleaned on uninstall (via _purge_project_artifacts)
"""

from __future__ import annotations

import shutil
from pathlib import Path

from opencontext_core.paths import is_owned, write_manifest

# ---------------------------------------------------------------------------
# is_owned gate — the predicate the uninstall command relies on
# ---------------------------------------------------------------------------


def test_uninstall_only_removes_owned_dir(tmp_path: Path) -> None:
    """is_owned is True for a dir with a valid manifest; False for siblings without one.

    This mirrors the uninstall logic: rmtree only when is_owned() returns True.
    """
    owned_dir = tmp_path / "owned_project"
    owned_dir.mkdir()
    write_manifest(owned_dir, tmp_path / "myproject", version="1.0.0")

    foreign_dir = tmp_path / "foreign_project"
    foreign_dir.mkdir()
    # No manifest written to foreign_dir.

    assert is_owned(owned_dir) is True
    assert is_owned(foreign_dir) is False

    # Simulate the uninstall gate: only remove owned_dir.
    for candidate in [owned_dir, foreign_dir]:
        if candidate.exists() and is_owned(candidate):
            shutil.rmtree(candidate)

    assert not owned_dir.exists(), "Owned dir should have been removed"
    assert foreign_dir.exists(), "Foreign dir must survive"


def test_is_owned_wrong_project_root_manifest(tmp_path: Path) -> None:
    """A manifest with a different project_root still returns is_owned True.

    The is_owned() predicate checks app == "opencontext"; project_root matching
    is the responsibility of the caller (uninstall). This test confirms is_owned
    does not falsely reject a manifest just because it records a different root.
    """
    dir_a = tmp_path / "dir_a"
    dir_a.mkdir()
    # Write manifest for project_root = tmp_path / "other_project"
    write_manifest(dir_a, tmp_path / "other_project", version="1.0.0")
    # is_owned only checks app field — should be True.
    assert is_owned(dir_a) is True


def test_uninstall_user_mode_cleans_xdg_state(xdg_state_tmp: Path, tmp_path: Path) -> None:
    """_purge_project_artifacts removes the XDG user-mode project dir when owned."""

    from opencontext_cli.commands.uninstall_cmd import _purge_project_artifacts
    from opencontext_core.paths import StorageMode, resolve_storage_path

    project_root = tmp_path / "myproject"
    project_root.mkdir()

    # Pre-create the XDG state dir and write a manifest so is_owned() passes.
    xdg_path = resolve_storage_path(project_root, StorageMode.user)
    xdg_path.mkdir(parents=True, exist_ok=True)
    write_manifest(xdg_path, project_root, version="1.0.0")

    assert xdg_path.exists()
    assert is_owned(xdg_path)

    # Run purge targeting the project root.
    _purge_project_artifacts(project_root)

    assert not xdg_path.exists(), f"XDG state dir {xdg_path} should have been removed by purge"


def test_uninstall_does_not_remove_foreign_manifest_dir(
    xdg_state_tmp: Path, tmp_path: Path
) -> None:
    """_purge_project_artifacts only removes the storage dir for the given root.

    A sibling dir for a *different* project should survive even if it has a valid
    manifest — because its project_id (derived from a different root) won't match
    the resolved path for the current project.
    """
    from opencontext_cli.commands.uninstall_cmd import _purge_project_artifacts
    from opencontext_core.paths import StorageMode, resolve_storage_path

    project_a = tmp_path / "project_a"
    project_a.mkdir()
    project_b = tmp_path / "project_b"
    project_b.mkdir()

    # Set up XDG state for project_b with a valid manifest.
    xdg_b = resolve_storage_path(project_b, StorageMode.user)
    xdg_b.mkdir(parents=True, exist_ok=True)
    write_manifest(xdg_b, project_b, version="1.0.0")

    assert xdg_b.exists()

    # Purge project_a — should NOT touch project_b's XDG dir.
    _purge_project_artifacts(project_a)

    assert xdg_b.exists(), (
        f"project_b XDG state {xdg_b} was incorrectly removed during project_a purge"
    )
