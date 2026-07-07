"""Execution-state artifacts must not accumulate inside project roots.

Product decision: in user mode (the default) ALL execution state (sessions,
runs, checkpoints, receipts, decision logs, learning state) lives under the
XDG project workspace; the repo keeps only user-facing config and SDD
deliverables. ``OPENCONTEXT_STORAGE_MODE=local`` preserves the legacy in-repo
layout byte-for-byte. Readers resolve the active location first and fall back
to the legacy in-repo tree for old runs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config_resolver import resolve_active_workspace_file
from opencontext_core.paths import StorageMode, resolve_storage_path
from opencontext_core.paths.execution_state import (
    checkpoints_root,
    execution_read_roots,
    execution_workspace,
    learning_root,
    receipts_root,
    runs_root,
    sessions_root,
)

_ROOT_RESOLVERS = {
    "sessions": sessions_root,
    "runs": runs_root,
    "checkpoints": checkpoints_root,
    "receipts": receipts_root,
    "learning": learning_root,
}


@pytest.fixture()
def local_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")


# --------------------------------------------------------------- resolver matrix


def test_execution_roots_user_mode_live_outside_project(
    tmp_path: Path, xdg_state_tmp: Path
) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    expected_base = resolve_storage_path(root, StorageMode.user) / "workspace"
    assert execution_workspace(root) == expected_base
    for name, resolver in _ROOT_RESOLVERS.items():
        resolved = resolver(root)
        assert resolved == expected_base / name
        assert not resolved.is_relative_to(root)
        assert str(resolved).startswith(str(xdg_state_tmp))


def test_execution_roots_local_mode_keep_legacy_layout(tmp_path: Path, local_mode: None) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    legacy = root.resolve() / ".opencontext"
    assert execution_workspace(root) == legacy
    for name, resolver in _ROOT_RESOLVERS.items():
        assert resolver(root) == legacy / name


def test_execution_roots_accept_str_root(tmp_path: Path, local_mode: None) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    assert runs_root(str(root)) == root.resolve() / ".opencontext" / "runs"


def test_execution_workspace_survives_malformed_config(tmp_path: Path, xdg_state_tmp: Path) -> None:
    """A malformed opencontext.yaml must not crash path resolution (defaults win)."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "opencontext.yaml").write_text("runtime: [unclosed\n", encoding="utf-8")
    assert execution_workspace(root) == resolve_storage_path(root, StorageMode.user) / "workspace"


def test_execution_workspace_malformed_config_honors_env_override(
    tmp_path: Path, local_mode: None
) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "opencontext.yaml").write_text("runtime: [unclosed\n", encoding="utf-8")
    assert execution_workspace(root) == root.resolve() / ".opencontext"


# ------------------------------------------------------------- reader fallback


def test_resolve_active_workspace_file_prefers_active(tmp_path: Path, xdg_state_tmp: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    active = execution_workspace(root) / "receipts" / "receipts.jsonl"
    legacy = root.resolve() / ".opencontext" / "receipts" / "receipts.jsonl"
    # Neither exists -> canonical (active) path so error messages name it.
    assert resolve_active_workspace_file(root, "receipts/receipts.jsonl") == active
    # Legacy only -> fall back to the old in-repo artifact.
    legacy.parent.mkdir(parents=True)
    legacy.write_text("{}", encoding="utf-8")
    assert resolve_active_workspace_file(root, "receipts/receipts.jsonl") == legacy
    # Both exist -> the active location wins.
    active.parent.mkdir(parents=True)
    active.write_text("{}", encoding="utf-8")
    assert resolve_active_workspace_file(root, "receipts/receipts.jsonl") == active


def test_execution_read_roots_active_first_then_legacy(tmp_path: Path, xdg_state_tmp: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    roots = execution_read_roots(root, "sessions")
    assert roots[0] == execution_workspace(root) / "sessions"
    assert roots[-1] == root.resolve() / ".opencontext" / "sessions"
    assert len(roots) == 2


def test_execution_read_roots_dedupes_in_local_mode(tmp_path: Path, local_mode: None) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    assert execution_read_roots(root, "sessions") == [root.resolve() / ".opencontext" / "sessions"]


# ------------------------------------------------------------- writer behaviour


def _exercise_execution_writers(root: Path) -> None:
    """Drive the execution-state writers a single `opencontext run` touches."""
    from opencontext_core.harness.checkpoint import CheckpointStore
    from opencontext_core.harness.run_store import RunStore
    from opencontext_core.harness.sessions import ensure_layout
    from opencontext_core.operating_model.receipts import RunReceipt, RunReceiptStore
    from opencontext_core.runtime.session import RuntimeSession
    from opencontext_core.runtime.session_store import SessionStore

    store = SessionStore(root)
    store.create_session(
        RuntimeSession(session_id="sess_x", root=str(root), task="t", profile="balanced")
    )
    ensure_layout(root, "sess_x", "run_x")
    RunStore(root).register("run_x", root / "elsewhere")
    victim = root / "src.py"
    victim.write_text("x = 1\n", encoding="utf-8")
    CheckpointStore(root).create([victim])
    RunReceiptStore(root).save(
        RunReceipt(
            run_id="run_x",
            workflow_id="fix",
            policy_hash="p",
            context_pack_hash="c",
            prompt_hash="h",
            provider="stub",
            model="stub",
            trace_id="trace_x",
            input_tokens=0,
            output_tokens=0,
        )
    )


def test_user_mode_run_writes_nothing_under_project_opencontext(
    tmp_path: Path, xdg_state_tmp: Path
) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    # Pre-existing config the installer creates stays untouched in-repo.
    config_dir = root / ".opencontext"
    config_dir.mkdir()
    (config_dir / "harness.yaml").write_text("version: '0.1'\n", encoding="utf-8")
    before = sorted(p.relative_to(root).as_posix() for p in config_dir.rglob("*"))

    _exercise_execution_writers(root)

    after = sorted(p.relative_to(root).as_posix() for p in config_dir.rglob("*"))
    assert after == before, f"execution state leaked into project root: {after}"
    workspace = execution_workspace(root)
    assert (workspace / "sessions" / "sess_x" / "session.json").is_file()
    assert (workspace / "sessions" / "sess_x" / "runs" / "run_x").is_dir()
    assert (workspace / "receipts" / "receipts.jsonl").is_file()
    assert any((workspace / "checkpoints").iterdir())


def test_local_mode_run_keeps_legacy_in_repo_layout(tmp_path: Path, local_mode: None) -> None:
    root = tmp_path / "proj"
    root.mkdir()

    _exercise_execution_writers(root)

    workspace = root / ".opencontext"
    assert (workspace / "sessions" / "sess_x" / "session.json").is_file()
    assert (workspace / "sessions" / "sess_x" / "runs" / "run_x").is_dir()
    assert (workspace / "receipts" / "receipts.jsonl").is_file()
    assert (workspace / "runs" / "index.json").is_file()
    assert any((workspace / "checkpoints").iterdir())


# --------------------------------------------------------- legacy-run readers


def test_readers_fall_back_to_legacy_runs_in_user_mode(tmp_path: Path, xdg_state_tmp: Path) -> None:
    from opencontext_core.context.pack_explain import locate_run_context_pack
    from opencontext_core.harness.sessions import find_run_root
    from opencontext_core.oc_flow.runner import OCFlowRunner

    root = tmp_path / "proj"
    root.mkdir()
    legacy_run = root / ".opencontext" / "sessions" / "s1" / "runs" / "r1"
    legacy_run.mkdir(parents=True)
    (legacy_run / "context-pack.json").write_text("{}", encoding="utf-8")

    assert find_run_root(root, "r1") == legacy_run
    assert locate_run_context_pack(root, "r1") == legacy_run / "context-pack.json"
    assert OCFlowRunner(root=root)._locate_run_dir("s1", "r1") == legacy_run

    # A run persisted at the active location wins over the legacy tree.
    active_run = sessions_root(root) / "s1" / "runs" / "r1"
    active_run.mkdir(parents=True)
    (active_run / "context-pack.json").write_text("{}", encoding="utf-8")
    assert find_run_root(root, "r1") == active_run
    assert locate_run_context_pack(root, "r1") == active_run / "context-pack.json"
