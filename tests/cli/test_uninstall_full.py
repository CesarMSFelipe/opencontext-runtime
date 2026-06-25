"""Tests for uninstall --full, --verify, and verify_no_traces."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from opencontext_cli.commands.uninstall_cmd import verify_no_traces


# ---------------------------------------------------------------------------
# verify_no_traces unit tests
# ---------------------------------------------------------------------------


def test_verify_no_traces_clean(tmp_path):
    assert verify_no_traces(tmp_path) == []


def test_verify_no_traces_detects_oc_agent_file(tmp_path):
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "oc-orchestrator.md").write_text("hello", encoding="utf-8")
    residue = verify_no_traces(tmp_path)
    assert any("oc-orchestrator.md" in r for r in residue)


def test_verify_no_traces_clean_after_removal(tmp_path):
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    f = agents_dir / "oc-orchestrator.md"
    f.write_text("hello", encoding="utf-8")
    assert verify_no_traces(tmp_path) != []
    f.unlink()
    assert verify_no_traces(tmp_path) == []


def test_verify_no_traces_detects_opencontext_dir(tmp_path):
    oc_dir = tmp_path / ".opencontext"
    oc_dir.mkdir()
    residue = verify_no_traces(tmp_path)
    assert any(".opencontext" in r for r in residue)


def test_verify_no_traces_detects_mcp_json(tmp_path):
    (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
    residue = verify_no_traces(tmp_path)
    assert any(".mcp.json" in r for r in residue)


# ---------------------------------------------------------------------------
# --full without --yes in non-TTY aborts
# ---------------------------------------------------------------------------


def test_full_without_yes_non_tty_exits(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    # Patch _resolve_flag in opencontext_cli.main so the import inside handle_uninstall
    # returns the value as-is (no env-var override).
    import opencontext_cli.main as main_mod

    monkeypatch.setattr(main_mod, "_resolve_flag", lambda v, _: v)
    args = SimpleNamespace(
        full=True,
        verify=False,
        yes=False,
        dry_run=False,
        json=False,
        scope="local",
        root=str(tmp_path),
        all_agents=False,
        agents=[],
        purge=False,
    )
    from opencontext_cli.commands.uninstall_cmd import handle_uninstall

    with pytest.raises(SystemExit) as exc_info:
        handle_uninstall(args)
    assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# --verify exits 0 when clean, 1 when traces remain
# ---------------------------------------------------------------------------


def test_verify_flag_exits_0_when_clean(tmp_path, monkeypatch):
    import opencontext_cli.main as main_mod

    monkeypatch.setattr(main_mod, "_resolve_flag", lambda v, _: v)
    args = SimpleNamespace(
        verify=True,
        full=False,
        yes=False,
        dry_run=False,
        json=False,
        scope="local",
        root=str(tmp_path),
        all_agents=False,
        agents=[],
        purge=False,
    )
    from opencontext_cli.commands.uninstall_cmd import handle_uninstall

    with pytest.raises(SystemExit) as exc_info:
        handle_uninstall(args)
    assert exc_info.value.code == 0


def test_verify_flag_exits_1_when_traces(tmp_path, monkeypatch):
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "oc-orchestrator.md").write_text("hi", encoding="utf-8")
    import opencontext_cli.main as main_mod

    monkeypatch.setattr(main_mod, "_resolve_flag", lambda v, _: v)
    args = SimpleNamespace(
        verify=True,
        full=False,
        yes=False,
        dry_run=False,
        json=False,
        scope="local",
        root=str(tmp_path),
        all_agents=False,
        agents=[],
        purge=False,
    )
    from opencontext_cli.commands.uninstall_cmd import handle_uninstall

    with pytest.raises(SystemExit) as exc_info:
        handle_uninstall(args)
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# --full does not delete untracked files
# ---------------------------------------------------------------------------


def test_full_does_not_delete_untracked(tmp_path, monkeypatch):
    """A user file not tracked in the ledger survives --full --yes."""
    user_file = tmp_path / "my_custom_file.txt"
    user_file.write_text("keep me", encoding="utf-8")

    import opencontext_cli.main as main_mod

    monkeypatch.setattr(main_mod, "_resolve_flag", lambda v, _: v)
    args = SimpleNamespace(
        full=True,
        verify=False,
        yes=True,
        dry_run=False,
        json=True,
        scope="local",
        root=str(tmp_path),
        all_agents=False,
        agents=[],
        purge=False,
    )
    from opencontext_cli.commands.uninstall_cmd import handle_uninstall

    handle_uninstall(args)

    assert user_file.exists()
    assert user_file.read_text(encoding="utf-8") == "keep me"
