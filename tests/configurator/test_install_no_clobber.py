"""Configuring an agent must never destroy the developer's own instructions."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.agent_installer import AgentInstaller, AgentTarget
from opencontext_core.configurator.constants import mcp_config_path
from opencontext_core.configurator.service import Configurator


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


# The per-shape merge is unit-tested in test_mcp_shapes.py; these cases prove the
# full Configurator.configure() path preserves a developer's existing MCP config
# across the divergent native shapes (JSON mcpServers / JSON servers / TOML / YAML),
# not just claude-code.
@pytest.mark.parametrize(
    "agent, seed_text, survives",
    [
        ("claude-code", '{"mcpServers": {"mine": {"command": "x"}}, "userKey": 1}', "mine"),
        ("vscode-copilot", '{"servers": {"mine": {"command": "x"}}}', "mine"),
        ("codex", 'model = "gpt-5"\n\n[mcp_servers.mine]\ncommand = "x"\n', "gpt-5"),
        ("continue", "mcpServers:\n  mine:\n    command: x\n", "mine"),
    ],
)
def test_configure_preserves_existing_mcp_per_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    agent: str,
    seed_text: str,
    survives: str,
) -> None:
    if agent == "continue":
        pytest.importorskip("yaml")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    path = mcp_config_path(agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(seed_text, encoding="utf-8")

    Configurator(project_root=tmp_path / "proj").configure([agent], scope="global")

    body = path.read_text(encoding="utf-8")
    assert survives in body  # developer's pre-existing server / key not dropped
    assert "opencontext" in body  # ours added in the agent's native shape
