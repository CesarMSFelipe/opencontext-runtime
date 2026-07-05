"""Tests for the 5-case project detection (T2.27).

Per strict-TDD: this file is the source of truth for the
``opencontext_memory.project.DetectProjectFull`` contract. The production
module lands in T2.28 to turn these RED tests GREEN; the
:func:`opencontext_memory.tools.mem_current_project.mem_current_project`
wrapper is refactored to delegate to ``DetectProjectFull`` in the same
batch so the existing PR2.c.i tests (``test_REQ_OMT_007_*``) keep passing
without modification.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from opencontext_memory.project import (
    DetectionResult,
    DetectProjectFull,
    available_projects,
)


def _write_git_repo(
    path: Path,
    *,
    remote_url: str | None = None,
    bare: bool = True,
) -> Path:
    """Create a fake git repo at ``path`` with an optional ``origin`` URL.

    The ``bare`` flag mirrors the layout ``mem_current_project`` parses
    (``.git/config`` with a ``[remote "origin"]`` block). Set ``bare=False``
    to write a config with a bare remote (``url = ...`` with no extra
    padding) — used by the recovery-token test.
    """
    path = Path(path)
    (path / ".git").mkdir(parents=True, exist_ok=True)
    lines = ["[core]", "    repositoryformatversion = 0"]
    if remote_url is not None:
        if bare:
            lines += ['[remote "origin"]', f"    url = {remote_url}"]
        else:
            lines += ['[remote "origin"]', f"url = {remote_url}"]
    (path / ".git" / "config").write_text("\n".join(lines) + "\n")
    return path


def _write_config(cwd: Path, project_name: str) -> None:
    (cwd / ".opencontext").mkdir(parents=True, exist_ok=True)
    (cwd / ".opencontext" / "config.json").write_text(json.dumps({"project_name": project_name}))


# ---------------------------------------------------------------------------
# REQ-OMPD-001 — 5-case detection
# ---------------------------------------------------------------------------


def test_REQ_OMPD_001_config_case_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`.opencontext/config.json` with `project_name` overrides everything else."""
    cwd = _write_git_repo(tmp_path / "alpha", remote_url="git@github.com:foo/bar.git")
    _write_config(cwd, project_name="alpha")
    monkeypatch.chdir(cwd)

    result = DetectProjectFull(cwd)

    assert result.project == "alpha"
    assert result.source == "config"


def test_REQ_OMPD_001_git_remote_case_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A git repo with origin returns the slugified repo name; config absent."""
    repo = _write_git_repo(tmp_path / "myproj", remote_url="git@github.com:foo/bar.git")
    monkeypatch.chdir(repo)

    result = DetectProjectFull(repo)

    assert result.project == "bar"
    assert result.source == "git_remote"


def test_REQ_OMPD_001_git_root_basename_no_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A git repo with NO origin falls back to the repo basename."""
    repo = _write_git_repo(tmp_path / "myproj")  # no remote
    monkeypatch.chdir(repo)

    result = DetectProjectFull(repo)

    assert result.project == "myproj"
    assert result.source == "git_root"


def test_REQ_OMPD_001_git_child_single_descendant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cwd has NO git ancestor but has exactly one descendant git repo → auto-promote."""
    parent = tmp_path / "workspace"
    parent.mkdir()
    _write_git_repo(parent / "only_one")  # no remote
    monkeypatch.chdir(parent)

    result = DetectProjectFull(parent)

    assert result.project == "only_one"
    assert result.source == "git_child"
    assert result.warning is not None
    assert "auto_promoted_child" in result.warning


def test_REQ_OMPD_001_git_child_multiple_descendants_is_ambiguous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cwd has two or more descendant git repos (no remote) → ambiguous_project."""
    parent = tmp_path / "workspace"
    parent.mkdir()
    _write_git_repo(parent / "proj_a")  # no remote
    _write_git_repo(parent / "proj_b")  # no remote
    monkeypatch.chdir(parent)

    result = DetectProjectFull(parent)

    assert result.error == "ambiguous_project"
    assert result.source == "ambiguous"
    assert set(result.available_projects) == {"proj_a", "proj_b"}
    assert result.recovery_token is not None


def test_REQ_OMPD_001_multiple_ancestor_git_no_remote_is_ambiguous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When cwd sits between two parent git dirs with no remote → ambiguous (legacy path)."""
    outer = _write_git_repo(tmp_path / "outer")
    inner_parent = outer / "inner"
    inner_parent.mkdir(parents=True, exist_ok=True)
    cwd = inner_parent / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)
    # Also nest a sibling git so we have two ancestors with no remote.
    (inner_parent / "sibling").mkdir(parents=True, exist_ok=True)
    (inner_parent / ".git").mkdir(parents=True, exist_ok=True)
    (inner_parent / ".git" / "config").write_text("[core]\n    repositoryformatversion = 0\n")
    (inner_parent / "sibling" / ".git").mkdir(parents=True, exist_ok=True)
    (inner_parent / "sibling" / ".git" / "config").write_text(
        "[core]\n    repositoryformatversion = 0\n"
    )
    monkeypatch.chdir(cwd)

    result = DetectProjectFull(cwd)

    assert result.error == "ambiguous_project"
    assert result.source == "ambiguous"
    assert result.recovery_token is not None


def test_REQ_OMPD_001_dir_basename_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No git anywhere → `cwd.name`."""
    cwd = tmp_path / "standalone"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    result = DetectProjectFull(cwd)

    assert result.project == "standalone"
    assert result.source == "dir_basename"
    assert result.warning is None
    assert result.error is None


# ---------------------------------------------------------------------------
# REQ-OMPD-004 — deterministic slug from remote URL
# ---------------------------------------------------------------------------


def test_REQ_OMPD_004_canonical_remote_url_deterministic_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same URL → same slug (idempotent across calls)."""
    repo = _write_git_repo(tmp_path / "p", remote_url="git@github.com:foo/Bar.git")
    monkeypatch.chdir(repo)

    first = DetectProjectFull(repo)
    second = DetectProjectFull(repo)

    assert first.project == "bar"
    assert first.project == second.project
    assert first.source == "git_remote"


def test_REQ_OMPD_004_https_url_matches_ssh_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTTPS form resolves to the same slug as the SSH form."""
    repo = _write_git_repo(tmp_path / "p", remote_url="https://github.com/foo/Bar.git")
    monkeypatch.chdir(repo)

    result = DetectProjectFull(repo)

    assert result.project == "bar"
    assert result.source == "git_remote"


# ---------------------------------------------------------------------------
# REQ-OMPD-002 — recovery token flow
# ---------------------------------------------------------------------------


def test_REQ_OMPD_002_recovery_token_accepts_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First ambiguous call → token returned. Second call w/ token selects cleanly."""
    parent = tmp_path / "workspace"
    parent.mkdir()
    _write_git_repo(parent / "proj_a")
    _write_git_repo(parent / "proj_b")
    monkeypatch.chdir(parent)

    first = DetectProjectFull(parent)
    assert first.error == "ambiguous_project"
    token = first.recovery_token
    assert token is not None

    second = DetectProjectFull(
        parent,
        recovery_token=token,
        selected_project="proj_b",
        project_choice_reason="user_selected_after_ambiguous_project",
    )

    assert second.project == "proj_b"
    assert second.source == "user_selected"
    assert second.error is None


def test_REQ_OMPD_002_invalid_recovery_token_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bogus token raises ``ValueError("invalid_recovery_token")``."""
    cwd = tmp_path / "lone"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    with pytest.raises(ValueError, match=r"^invalid_recovery_token$"):
        DetectProjectFull(cwd, recovery_token="WRONG", selected_project="x")


def test_REQ_OMPD_002_missing_project_choice_reason_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even with a valid token, ``project_choice_reason`` must be the spec'd string."""
    parent = tmp_path / "workspace"
    parent.mkdir()
    _write_git_repo(parent / "proj_a")
    _write_git_repo(parent / "proj_b")
    monkeypatch.chdir(parent)

    first = DetectProjectFull(parent)
    token = first.recovery_token

    with pytest.raises(ValueError, match=r"^invalid_recovery_token$"):
        DetectProjectFull(parent, recovery_token=token, selected_project="proj_a")


# ---------------------------------------------------------------------------
# REQ-OMPD-005 — DetectionResult shape + JSON round-trip
# ---------------------------------------------------------------------------


def test_REQ_OMPD_005_detection_result_json_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All fields round-trip through JSON without loss."""
    parent = tmp_path / "workspace"
    parent.mkdir()
    _write_git_repo(parent / "a")
    _write_git_repo(parent / "b")
    monkeypatch.chdir(parent)

    result = DetectProjectFull(parent)
    payload = result.model_dump_json()
    rehydrated = DetectionResult.model_validate_json(payload)

    assert rehydrated == result
    assert rehydrated.recovery_token == result.recovery_token
    assert rehydrated.available_projects == result.available_projects


def test_REQ_OMPD_005_available_projects_empty_for_unambiguous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``available_projects`` defaults to ``[]`` outside of the ambiguous branch."""
    repo = _write_git_repo(tmp_path / "p", remote_url="git@github.com:foo/bar.git")
    monkeypatch.chdir(repo)

    result = DetectProjectFull(repo)

    assert available_projects(result) == []
