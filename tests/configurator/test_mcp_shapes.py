"""Each agent's MCP config must land under its native root key and format.

The historical bug wrote ``mcpServers`` for every client. VS Code/Copilot use
``servers``, Codex uses TOML ``[mcp_servers.<name>]``, and Continue uses YAML.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from opencontext_core.configurator.mcp_strategy import McpShape, write_mcp_servers

_SERVER = {
    "opencontext": {
        "type": "stdio",
        "command": "opencontext",
        "args": ["mcp"],
    }
}


def test_emitted_mcp_command_parses_against_the_cli() -> None:
    """The launch command we write into every agent must be a real CLI invocation.

    Regression: the entry pointed at a non-existent ``serve`` subcommand, so every
    configured agent got an MCP launch command that exits with argparse error.
    """
    from opencontext_cli.main import _build_parser
    from opencontext_core.configurator.constants import MCP_SERVER_ENTRY

    parser = _build_parser()
    args = parser.parse_args(list(MCP_SERVER_ENTRY["args"]))
    assert args.command == "mcp"


def test_json_mcp_servers_shape(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    write_mcp_servers(path, _SERVER, shape=McpShape.JSON_MCP_SERVERS)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "opencontext" in data["mcpServers"]
    assert "servers" not in data


def test_json_servers_shape_for_vscode(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    write_mcp_servers(path, _SERVER, shape=McpShape.JSON_SERVERS)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "opencontext" in data["servers"]
    assert "mcpServers" not in data


def test_toml_mcp_servers_shape_for_codex(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    write_mcp_servers(path, _SERVER, shape=McpShape.TOML_MCP_SERVERS)
    parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    assert "opencontext" in parsed["mcp_servers"]
    assert parsed["mcp_servers"]["opencontext"]["command"] == "opencontext"
    assert parsed["mcp_servers"]["opencontext"]["args"] == ["mcp"]


def test_yaml_mcp_servers_shape_for_continue(tmp_path: Path) -> None:
    yaml = pytest.importorskip("yaml")
    path = tmp_path / "config.yaml"
    write_mcp_servers(path, _SERVER, shape=McpShape.YAML_MCP_SERVERS)
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "opencontext" in parsed["mcpServers"]


def test_json_merge_preserves_existing_servers(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    path.write_text(
        json.dumps({"mcpServers": {"other": {"command": "x"}}, "userKey": 1}),
        encoding="utf-8",
    )
    write_mcp_servers(path, _SERVER, shape=McpShape.JSON_MCP_SERVERS)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert "opencontext" in data["mcpServers"]
    assert data["userKey"] == 1


def test_toml_merge_preserves_existing_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        'model = "gpt-5"\n\n[mcp_servers.other]\ncommand = "x"\n',
        encoding="utf-8",
    )
    write_mcp_servers(path, _SERVER, shape=McpShape.TOML_MCP_SERVERS)
    parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    assert parsed["model"] == "gpt-5"
    assert "other" in parsed["mcp_servers"]
    assert "opencontext" in parsed["mcp_servers"]


def test_toml_upsert_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    write_mcp_servers(path, _SERVER, shape=McpShape.TOML_MCP_SERVERS)
    write_mcp_servers(path, _SERVER, shape=McpShape.TOML_MCP_SERVERS)
    text = path.read_text(encoding="utf-8")
    assert text.count("[mcp_servers.opencontext]") == 1
    parsed = tomllib.loads(text)
    assert "opencontext" in parsed["mcp_servers"]


def test_json_write_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "mcp.json"
    assert write_mcp_servers(path, _SERVER, shape=McpShape.JSON_MCP_SERVERS) is True
    assert write_mcp_servers(path, _SERVER, shape=McpShape.JSON_MCP_SERVERS) is False
