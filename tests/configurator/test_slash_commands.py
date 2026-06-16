"""Native slash-commands make OpenContext actions one keystroke in the agent."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.configurator import constants
from opencontext_core.configurator.service import Configurator


def test_configure_writes_claude_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    project = tmp_path / "proj"
    project.mkdir()

    Configurator(project_root=project).configure(["claude-code"], scope="local")

    cmd_dir = project / ".claude" / "commands"
    written = {p.name for p in cmd_dir.glob("*.md")}
    assert written == {f"{name}.md" for name, _d, _b in constants.OPENCONTEXT_COMMANDS}
    body = (cmd_dir / "oc-context.md").read_text(encoding="utf-8")
    assert "description:" in body and "$ARGUMENTS" in body
    assert "opencontext_context" in body


def test_uninstall_removes_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    project = tmp_path / "proj"
    project.mkdir()
    cfg = Configurator(project_root=project)
    cfg.configure(["claude-code"], scope="local")
    assert list((project / ".claude" / "commands").glob("oc-*.md"))

    cfg.deconfigure(["claude-code"], scope="local")
    assert not list((project / ".claude" / "commands").glob("oc-*.md"))


def test_agent_without_command_dir_writes_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    project = tmp_path / "proj"
    project.mkdir()
    Configurator(project_root=project).configure(["codex"], scope="local")
    assert constants.command_dir("codex") is None
