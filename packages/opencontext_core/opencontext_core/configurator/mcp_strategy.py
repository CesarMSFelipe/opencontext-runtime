"""Write MCP server entries in each client's native shape.

Clients disagree on where MCP servers live:
- JSON ``mcpServers`` (claude-code, cursor, windsurf, gemini-cli settings, cline, roo)
- JSON ``servers`` (VS Code / Copilot ``.vscode/mcp.json``)
- TOML ``[mcp_servers.<name>]`` (codex ``~/.codex/config.toml``)
- YAML ``mcpServers`` (continue)

Every writer merges into existing config and is idempotent.
"""

from __future__ import annotations

import json
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Any

from opencontext_core.configurator.filemerge import merge_mcp_servers, write_text_atomic


class McpShape(StrEnum):
    """How a client stores MCP server definitions on disk."""

    JSON_MCP_SERVERS = "json_mcp_servers"
    JSON_SERVERS = "json_servers"
    TOML_MCP_SERVERS = "toml_mcp_servers"
    YAML_MCP_SERVERS = "yaml_mcp_servers"


def write_mcp_servers(path: Path, servers: dict[str, Any], *, shape: McpShape) -> bool:
    """Merge ``servers`` into the config at ``path`` using the client's shape.

    Returns ``True`` if the file changed, ``False`` if it was already current.
    """

    path = Path(path)
    if shape is McpShape.JSON_MCP_SERVERS:
        return _write_json(path, servers, root_key="mcpServers")
    if shape is McpShape.JSON_SERVERS:
        return _write_json(path, servers, root_key="servers")
    if shape is McpShape.TOML_MCP_SERVERS:
        return _write_toml(path, servers)
    if shape is McpShape.YAML_MCP_SERVERS:
        return _write_yaml(path, servers)
    raise ValueError(f"unsupported MCP shape: {shape}")


def _write_json(path: Path, servers: dict[str, Any], *, root_key: str) -> bool:
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    merged = merge_mcp_servers(existing, servers, root_key=root_key)
    return write_text_atomic(path, json.dumps(merged, indent=2) + "\n")


def _write_yaml(path: Path, servers: dict[str, Any]) -> bool:
    import yaml

    existing: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (yaml.YAMLError, OSError):
            existing = {}
    merged = merge_mcp_servers(existing, servers, root_key="mcpServers")
    return write_text_atomic(path, yaml.safe_dump(merged, sort_keys=False))


def _write_toml(path: Path, servers: dict[str, Any]) -> bool:
    """Upsert ``[mcp_servers.<name>]`` tables without a TOML writer dependency.

    Reads existing TOML with stdlib ``tomllib`` to detect which server tables are
    already present, then appends only the missing ones as text. Existing content
    (other keys and other servers) is preserved byte-for-byte.
    """

    text = ""
    parsed: dict[str, Any] = {}
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
            parsed = tomllib.loads(text)
        except (tomllib.TOMLDecodeError, OSError):
            text = path.read_text(encoding="utf-8") if path.exists() else ""
            parsed = {}

    existing_servers = parsed.get("mcp_servers")
    existing_names = set(existing_servers) if isinstance(existing_servers, dict) else set()

    blocks: list[str] = []
    for name, entry in servers.items():
        if name in existing_names:
            continue
        blocks.append(_toml_server_block(name, entry))

    if not blocks:
        return False

    base = text.rstrip("\n")
    addition = "\n\n".join(blocks)
    new_text = f"{base}\n\n{addition}\n" if base else f"{addition}\n"
    return write_text_atomic(path, new_text)


def _toml_server_block(name: str, entry: dict[str, Any]) -> str:
    lines = [f"[mcp_servers.{name}]"]
    for key, value in entry.items():
        lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return json.dumps(str(value))
