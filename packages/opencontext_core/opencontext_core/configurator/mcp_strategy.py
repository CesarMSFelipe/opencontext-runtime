"""Write MCP server entries in each client's native shape.

Clients disagree on where MCP servers live:
- JSON ``mcpServers`` (claude-code, cursor, windsurf, gemini-cli settings, cline, roo)
- JSON ``servers`` (VS Code / Copilot ``.vscode/mcp.json``)
- JSON ``mcp`` with ``{"type": "local", "command": [cmd, *args]}`` entries
  (opencode ``opencode.json``)
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
    JSON_OPENCODE_MCP = "json_opencode_mcp"
    TOML_MCP_SERVERS = "toml_mcp_servers"
    YAML_MCP_SERVERS = "yaml_mcp_servers"


def write_mcp_servers(path: Path, servers: dict[str, Any], *, shape: McpShape) -> bool:
    """Merge ``servers`` into the config at ``path`` using the client's shape.

    Returns ``True`` if the file changed, ``False`` if it was already current.
    """

    _, content = plan_mcp_servers(path, servers, shape=shape)
    if content is None:
        return False
    return write_text_atomic(Path(path), content)


def plan_mcp_servers(
    path: Path, servers: dict[str, Any], *, shape: McpShape
) -> tuple[Path, str | None]:
    """Compute the file and its merged content without writing.

    Returns ``(path, content)`` where ``content`` is the exact text that would be
    written, or ``None`` if the file is already current (a no-op write).
    """

    path = Path(path)
    if shape is McpShape.JSON_MCP_SERVERS:
        return path, _plan_json(path, servers, root_key="mcpServers")
    if shape is McpShape.JSON_SERVERS:
        return path, _plan_json(path, servers, root_key="servers")
    if shape is McpShape.JSON_OPENCODE_MCP:
        return path, _plan_json(path, _to_opencode_entries(servers), root_key="mcp")
    if shape is McpShape.TOML_MCP_SERVERS:
        return path, _plan_toml(path, servers)
    if shape is McpShape.YAML_MCP_SERVERS:
        return path, _plan_yaml(path, servers)
    raise ValueError(f"unsupported MCP shape: {shape}")


def _to_opencode_entries(servers: dict[str, Any]) -> dict[str, Any]:
    """Translate canonical ``{command, args}`` entries into OpenCode's format.

    OpenCode expects ``{"type": "local", "command": [cmd, *args], "enabled": true}``
    under a root ``mcp`` key; it does not read the ``mcpServers`` wire shape.
    """

    translated: dict[str, Any] = {}
    for name, entry in servers.items():
        command = entry.get("command", "")
        args = list(entry.get("args", []))
        translated[name] = {
            "type": "local",
            "command": [command, *args],
            "enabled": True,
        }
    return translated


def remove_mcp_server(path: Path, name: str, *, shape: McpShape) -> bool:
    """Remove a single MCP server entry from the config, preserving the rest.

    Returns ``True`` if the file changed. The user's other servers and keys are
    untouched; an absent entry (or missing file) is a no-op.
    """

    path = Path(path)
    if not path.exists():
        return False
    if shape in (McpShape.JSON_MCP_SERVERS, McpShape.JSON_SERVERS, McpShape.JSON_OPENCODE_MCP):
        root_key = {
            McpShape.JSON_MCP_SERVERS: "mcpServers",
            McpShape.JSON_SERVERS: "servers",
            McpShape.JSON_OPENCODE_MCP: "mcp",
        }[shape]
        content = _plan_remove_json(path, name, root_key=root_key)
    elif shape is McpShape.YAML_MCP_SERVERS:
        content = _plan_remove_yaml(path, name)
    elif shape is McpShape.TOML_MCP_SERVERS:
        content = _plan_remove_toml(path, name)
    else:
        raise ValueError(f"unsupported MCP shape: {shape}")
    if content is None:
        return False
    return write_text_atomic(path, content)


def _plan_remove_json(path: Path, name: str, *, root_key: str) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    servers = data.get(root_key)
    if not isinstance(servers, dict) or name not in servers:
        return None
    del servers[name]
    if not servers:
        del data[root_key]
    content = json.dumps(data, indent=2) + "\n"
    return None if _unchanged(path, content) else content


def _plan_remove_yaml(path: Path, name: str) -> str | None:
    import yaml

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or name not in servers:
        return None
    del servers[name]
    if not servers:
        del data["mcpServers"]
    content: str = yaml.safe_dump(data, sort_keys=False)
    return None if _unchanged(path, content) else content


def _plan_remove_toml(path: Path, name: str) -> str | None:
    """Delete the ``[mcp_servers.<name>]`` table block from TOML text.

    Text-based to match the append-only writer and preserve everything else
    byte-for-byte. Removes from the table header through the line before the next
    top-level ``[`` table (or EOF).
    """

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    header = f"[mcp_servers.{name}]"
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.strip() == header), None)
    if start is None:
        return None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("["):
            end = i
            break
    del lines[start:end]
    while lines and lines[-1].strip() == "":
        lines.pop()
    content = ("\n".join(lines) + "\n") if lines else ""
    return None if _unchanged(path, content) else content


def _unchanged(path: Path, content: str) -> bool:
    if not path.exists():
        return False
    try:
        return path.read_text(encoding="utf-8") == content
    except OSError:
        return False


def _plan_json(path: Path, servers: dict[str, Any], *, root_key: str) -> str | None:
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    merged = merge_mcp_servers(existing, servers, root_key=root_key)
    content = json.dumps(merged, indent=2) + "\n"
    return None if _unchanged(path, content) else content


def _plan_yaml(path: Path, servers: dict[str, Any]) -> str | None:
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
    content: str = yaml.safe_dump(merged, sort_keys=False)
    return None if _unchanged(path, content) else content


def _plan_toml(path: Path, servers: dict[str, Any]) -> str | None:
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
        return None

    base = text.rstrip("\n")
    addition = "\n\n".join(blocks)
    return f"{base}\n\n{addition}\n" if base else f"{addition}\n"


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
