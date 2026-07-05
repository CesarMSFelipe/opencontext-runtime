"""Setup prepares AGENTS.md with stack standards (local scope, best-effort)."""

from __future__ import annotations

from pathlib import Path

from opencontext_cli.commands.setup_cmd import _maybe_write_stack_standards


def test_local_scope_writes_stack_block(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    report: dict[str, object] = {}

    _maybe_write_stack_standards(str(tmp_path), "local", report)

    body = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- opencontext:stack:start -->" in body
    assert "### Python" in body
    assert report.get("stack_standards") == ["python"]
    assert _maybe_write_stack_standards(str(tmp_path), "local", report) == []


def test_global_scope_does_not_write_project_file(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    report: dict[str, object] = {}

    _maybe_write_stack_standards(str(tmp_path), "global", report)

    assert not (tmp_path / "AGENTS.md").exists()
    assert "stack_standards" not in report
