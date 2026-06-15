"""Configuring an agent must never destroy the developer's own instructions."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.agent_installer import AgentInstaller, AgentTarget


def test_install_preserves_user_claude_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "CLAUDE.md").write_text(
        "# My rules\n\nMy own important instructions.\n", encoding="utf-8"
    )

    AgentInstaller(project_root=tmp_path).install([AgentTarget.CLAUDE_CODE], location="global")

    after = (claude_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert "My own important instructions." in after  # user content survives
    assert "<!-- opencontext:instructions:start -->" in after  # managed block added


def test_reinstall_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".claude").mkdir(parents=True)

    inst = AgentInstaller(project_root=tmp_path)
    inst.install([AgentTarget.CLAUDE_CODE], location="global")
    inst.install([AgentTarget.CLAUDE_CODE], location="global")

    text = (tmp_path / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.count("<!-- opencontext:instructions:start -->") == 1  # no duplication
