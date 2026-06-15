"""Uninstall must remove only OpenContext's managed config, never user content."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.configurator.constants import mcp_config_path
from opencontext_core.configurator.mcp_strategy import McpShape, remove_mcp_server
from opencontext_core.configurator.service import Configurator


@pytest.mark.parametrize(
    "shape, seed, user_token, root_key",
    [
        (
            McpShape.JSON_MCP_SERVERS,
            '{"mcpServers": {"mine": {"command": "x"}, "opencontext": {"command": "opencontext"}},'
            ' "userKey": 1}',
            "mine",
            "mcpServers",
        ),
        (
            McpShape.JSON_SERVERS,
            '{"servers": {"mine": {"command": "x"}, "opencontext": {"command": "opencontext"}}}',
            "mine",
            "servers",
        ),
        (
            McpShape.TOML_MCP_SERVERS,
            'model = "gpt-5"\n\n[mcp_servers.mine]\ncommand = "x"\n\n'
            '[mcp_servers.opencontext]\ncommand = "opencontext"\n',
            "gpt-5",
            None,
        ),
        (
            McpShape.YAML_MCP_SERVERS,
            "mcpServers:\n  mine:\n    command: x\n  opencontext:\n    command: opencontext\n",
            "mine",
            None,
        ),
    ],
)
def test_remove_mcp_server_keeps_user_servers(
    tmp_path: Path, shape: McpShape, seed: str, user_token: str, root_key: str | None
) -> None:
    if shape is McpShape.TOML_MCP_SERVERS:
        name = "config.toml"
    elif shape is McpShape.YAML_MCP_SERVERS:
        name = "config.yaml"
    else:
        name = "mcp.json"
    path = tmp_path / name
    path.write_text(seed, encoding="utf-8")

    changed = remove_mcp_server(path, "opencontext", shape=shape)

    assert changed is True
    body = path.read_text(encoding="utf-8")
    assert "opencontext" not in body  # ours removed
    assert user_token in body  # the developer's server/key survives
    # Removing again is a no-op.
    assert remove_mcp_server(path, "opencontext", shape=shape) is False


def test_remove_mcp_server_missing_file_is_noop(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    assert remove_mcp_server(missing, "opencontext", shape=McpShape.JSON_MCP_SERVERS) is False


def test_configure_then_uninstall_preserves_user_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("# Mine\n\nKEEP THIS LINE.\n", encoding="utf-8")
    mcp = mcp_config_path("claude-code")
    mcp.parent.mkdir(parents=True, exist_ok=True)
    mcp.write_text(json.dumps({"mcpServers": {"mine": {"command": "x"}}}), encoding="utf-8")

    cfg = Configurator(project_root=tmp_path / "proj")
    cfg.configure(["claude-code"], scope="global")
    # After configure: our block + server are present.
    assert "opencontext:instructions:start" in (claude / "CLAUDE.md").read_text(encoding="utf-8")
    assert "opencontext" in mcp.read_text(encoding="utf-8")

    report = cfg.deconfigure(["claude-code"], scope="global")

    assert report["agents_removed"] == 1
    after_md = (claude / "CLAUDE.md").read_text(encoding="utf-8")
    assert "KEEP THIS LINE." in after_md  # user content survives
    assert "opencontext:instructions" not in after_md  # our block removed
    after_mcp = json.loads(mcp.read_text(encoding="utf-8"))
    assert "mine" in after_mcp["mcpServers"]  # user's server survives
    assert "opencontext" not in after_mcp.get("mcpServers", {})  # ours removed


def test_uninstall_dry_run_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".claude").mkdir(parents=True)
    cfg = Configurator(project_root=tmp_path / "proj")
    cfg.configure(["claude-code"], scope="global")
    before = (tmp_path / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")

    report = cfg.deconfigure(["claude-code"], scope="global", dry_run=True)

    assert report["dry_run"] is True
    assert (tmp_path / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == before
