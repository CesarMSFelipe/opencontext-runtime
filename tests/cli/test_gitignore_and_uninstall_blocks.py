"""Setup manages a .gitignore block; uninstall strips project-level blocks clean."""

from __future__ import annotations

from pathlib import Path

from opencontext_cli.commands.setup_cmd import _maybe_write_gitignore
from opencontext_cli.commands.uninstall_cmd import _strip_project_managed_blocks


def test_gitignore_block_added_local_preserving_user_lines(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("*.log\nmy_secrets/\n", encoding="utf-8")

    _maybe_write_gitignore(str(tmp_path), "local")

    body = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "*.log" in body and "my_secrets/" in body  # user lines preserved
    assert ".storage/" in body and ".opencontext/" in body
    assert "# opencontext:storage:start" in body


def test_gitignore_skipped_for_global_scope(tmp_path: Path) -> None:
    _maybe_write_gitignore(str(tmp_path), "global")
    assert not (tmp_path / ".gitignore").exists()


def test_uninstall_strips_project_blocks_preserving_user_content(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# My rules\n\nkeep me\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")
    # Setup adds the managed blocks…
    _maybe_write_gitignore(str(tmp_path), "local")
    from opencontext_cli.commands.stack_cmd import write_stack_standards

    write_stack_standards(tmp_path)  # adds the AGENTS.md stack block (generic fallback)

    # …uninstall removes them, leaving user content intact.
    _strip_project_managed_blocks(str(tmp_path), "local")

    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "keep me" in agents
    assert "opencontext:stack" not in agents
    assert "*.log" in gitignore
    assert "opencontext:storage" not in gitignore
    assert ".storage/" not in gitignore
