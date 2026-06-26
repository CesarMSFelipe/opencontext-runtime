"""--full uninstall must strip the managed .gitignore storage block and verify must catch it.

Regression: _run_full_uninstall purged artifacts but never called
_strip_project_managed_blocks, and verify_no_traces did not inspect .gitignore —
so the `# opencontext:storage` block survived `--full` while verify reported clean.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_cli.commands.uninstall_cmd import (
    _run_full_uninstall,
    verify_no_traces,
)

_BLOCK = (
    "node_modules/\n"
    "# opencontext:storage:start\n"
    ".storage/\n"
    ".opencontext/\n"
    "# opencontext:storage:end\n"
)


def test_full_uninstall_strips_storage_block(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(_BLOCK, encoding="utf-8")

    _run_full_uninstall(tmp_path, scope="local", json_output=False)

    text = gitignore.read_text(encoding="utf-8")
    assert "opencontext:storage" not in text  # managed block gone
    assert "node_modules/" in text  # user content preserved


def test_verify_flags_leftover_gitignore_block(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(_BLOCK, encoding="utf-8")
    residue = verify_no_traces(tmp_path)
    assert any(".gitignore" in r for r in residue)


def test_verify_clean_without_block(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    assert verify_no_traces(tmp_path) == []
