"""Uninstall vs user-mode (XDG) execution state.

Execution artifacts live under ``$XDG_STATE_HOME/opencontext/projects/<hash>/``
in user mode. Pins the three uninstall promises around that tree:

* the global purge removes the whole XDG state root, project-hash execution
  state included;
* the workspace purge removes THIS project's owned XDG state dir and leaves
  other projects' state alone;
* the workspace-scope verify never flags XDG global state as residue — it is
  HOME-level state owned by the global scope.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_cli.commands.uninstall_cmd import (
    _purge_global_state,
    _purge_project_artifacts,
    verify_no_traces,
)
from opencontext_core.paths import StorageMode, resolve_storage_path, write_manifest


def _isolate_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


@pytest.fixture()
def user_mode_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, xdg_state_tmp: Path
) -> tuple[Path, Path]:
    """An isolated project whose XDG state dir holds execution artifacts."""
    _isolate_home(monkeypatch, tmp_path / "home")
    root = tmp_path / "project"
    root.mkdir()
    state_dir = resolve_storage_path(root, StorageMode.user)
    write_manifest(state_dir, root, version="test")
    run_state = state_dir / "workspace" / "sessions" / "sess_1" / "runs" / "run_1" / "state.json"
    run_state.parent.mkdir(parents=True)
    run_state.write_text(json.dumps({"run_id": "run_1", "status": "completed"}), encoding="utf-8")
    return root, state_dir


def test_global_purge_removes_xdg_project_execution_state(
    user_mode_project: tuple[Path, Path], xdg_state_tmp: Path
) -> None:
    _root, state_dir = user_mode_project
    assert state_dir.is_dir()

    removed = _purge_global_state()

    xdg_root = xdg_state_tmp / "opencontext"
    assert not xdg_root.exists(), "the global purge must remove the XDG state root"
    assert not state_dir.exists(), "project-hash execution state must go with it"
    assert str(xdg_root) in removed


def test_workspace_purge_removes_only_this_projects_xdg_state(
    user_mode_project: tuple[Path, Path], tmp_path: Path
) -> None:
    root, state_dir = user_mode_project
    other_root = tmp_path / "other-project"
    other_root.mkdir()
    other_state = resolve_storage_path(other_root, StorageMode.user)
    write_manifest(other_state, other_root, version="test")

    _purge_project_artifacts(root)

    assert not state_dir.exists(), "the owned XDG state dir for this project must be purged"
    assert other_state.exists(), "another project's XDG state must survive a workspace purge"


def test_workspace_verify_ignores_xdg_global_state(
    user_mode_project: tuple[Path, Path],
) -> None:
    root, state_dir = user_mode_project
    assert state_dir.is_dir()

    assert verify_no_traces(root) == [], (
        "workspace-scope verify must not flag XDG global state as residue"
    )


def test_uninstall_preview_ignores_xdg_global_state(
    user_mode_project: tuple[Path, Path],
) -> None:
    from opencontext_cli.tui.screens.uninstall_preview import build_uninstall_preview

    root, state_dir = user_mode_project
    assert state_dir.is_dir()

    preview = build_uninstall_preview(root)

    assert not any(str(state_dir) in trace for trace in preview["possible_residue"]), (
        "the uninstall preview (workspace scope) must not report XDG state as residue"
    )
