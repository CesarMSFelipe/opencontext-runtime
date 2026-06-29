"""--full uninstall must strip the managed .gitignore storage block and verify must catch it.

Regression: _run_full_uninstall purged artifacts but never called
_strip_project_managed_blocks, and verify_no_traces did not inspect .gitignore —
so the `# opencontext:storage` block survived `--full` while verify reported clean.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_cli.commands.uninstall_cmd import (
    _run_full_uninstall,
    _strip_project_managed_blocks,
    verify_no_traces,
)

_BLOCK = (
    "node_modules/\n"
    "# opencontext:storage:start\n"
    ".storage/\n"
    ".opencontext/\n"
    "# opencontext:storage:end\n"
)


def test_full_uninstall_strips_storage_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Isolate HOME so _run_full_uninstall's agent detection/deconfigure cannot touch
    # the developer's real global config; only the project .gitignore matters here.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
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


# ---------------------------------------------------------------------------
# Empty-after-strip files install created are unlinked, not left as 0-byte orphans
# ---------------------------------------------------------------------------

_ONLY_OUR_GITIGNORE = (
    "# opencontext:storage:start\n.storage/\n.opencontext/\n# opencontext:storage:end\n"
)
_ONLY_OUR_STACK = "<!-- opencontext:stack:start -->\nstandards\n<!-- opencontext:stack:end -->\n"


def test_strip_unlinks_gitignore_holding_only_our_block(tmp_path: Path) -> None:
    gi = tmp_path / ".gitignore"
    gi.write_text(_ONLY_OUR_GITIGNORE, encoding="utf-8")
    _strip_project_managed_blocks(tmp_path, "local")
    assert not gi.exists(), ".gitignore that held only our block must be removed, not left empty"


def test_strip_keeps_gitignore_with_user_lines(tmp_path: Path) -> None:
    gi = tmp_path / ".gitignore"
    gi.write_text(_BLOCK, encoding="utf-8")  # user node_modules/ + our block
    _strip_project_managed_blocks(tmp_path, "local")
    assert gi.exists()
    text = gi.read_text(encoding="utf-8")
    assert "node_modules/" in text and "opencontext:storage" not in text


def test_strip_keeps_user_gitignore_without_our_block(tmp_path: Path) -> None:
    gi = tmp_path / ".gitignore"
    gi.write_text("node_modules/\n", encoding="utf-8")
    _strip_project_managed_blocks(tmp_path, "local")
    assert gi.exists() and gi.read_text(encoding="utf-8") == "node_modules/\n"


def test_strip_unlinks_agents_md_holding_only_our_stack_block(tmp_path: Path) -> None:
    am = tmp_path / "AGENTS.md"
    am.write_text(_ONLY_OUR_STACK, encoding="utf-8")
    _strip_project_managed_blocks(tmp_path, "local")
    assert not am.exists(), "AGENTS.md that held only our stack block must be removed"
