"""Reversible, idempotent merges into files a developer co-owns.

Three modes, all non-destructive:
- ``inject_managed_section`` owns only a marker-delimited block inside Markdown the
  user also edits; content outside the markers is never touched, and empty content
  removes the block (clean uninstall).
- ``merge_mcp_servers`` deep-merges server entries under the client's root key,
  preserving every other key the user has configured.
- ``write_text_atomic`` writes via temp-file + rename, skips byte-identical writes,
  and refuses to follow symlinks.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_START = "<!-- opencontext:{id}:start -->"
_END = "<!-- opencontext:{id}:end -->"


def inject_managed_section(existing: str, section_id: str, content: str) -> str:
    """Insert or replace one managed Markdown block, leaving all else intact.

    Empty ``content`` removes the block entirely. Re-running is idempotent.
    """

    start = _START.format(id=section_id)
    end = _END.format(id=section_id)
    block = "" if not content.strip() else f"{start}\n{content.rstrip()}\n{end}\n"

    s = existing.find(start)
    e = existing.find(end)
    if s != -1 and e != -1 and e > s:
        before = existing[:s].rstrip("\n")
        after = existing[e + len(end) :].lstrip("\n")
        parts = [p for p in (before, block.rstrip("\n"), after) if p]
        return ("\n\n".join(parts) + "\n") if parts else ""

    if not block:
        return existing
    base = existing.rstrip("\n")
    return f"{base}\n\n{block}" if base else block


def inject_managed_lines(existing: str, section_id: str, lines: list[str]) -> str:
    """Insert/replace a ``#``-comment managed block in a line-based file.

    For ignore files (.cursorignore, etc.) which are not Markdown: owns only the
    block between ``# opencontext:<id>:start/end`` markers, leaving the user's own
    patterns intact. Empty ``lines`` removes the block (clean uninstall).
    """

    start = f"# opencontext:{section_id}:start"
    end = f"# opencontext:{section_id}:end"
    block = "" if not lines else "\n".join([start, *lines, end]) + "\n"

    s = existing.find(start)
    e = existing.find(end)
    if s != -1 and e != -1 and e > s:
        before = existing[:s].rstrip("\n")
        after = existing[e + len(end) :].lstrip("\n")
        parts = [p for p in (before, block.rstrip("\n"), after) if p]
        return ("\n\n".join(parts) + "\n") if parts else ""

    if not block:
        return existing
    base = existing.rstrip("\n")
    return f"{base}\n\n{block}" if base else block


def merge_mcp_servers(
    existing: dict[str, Any], servers: dict[str, Any], *, root_key: str = "mcpServers"
) -> dict[str, Any]:
    """Deep-merge MCP server entries under ``root_key`` (e.g. ``mcpServers`` or
    ``servers`` for VS Code), preserving the user's other servers and keys."""

    merged = _deep_merge(existing, {root_key: servers})
    return merged


def write_text_atomic(path: Path, content: str) -> bool:
    """Write ``content`` atomically. Return ``False`` if the file already matches.

    Refuses to write through a symlink (raises ``ValueError``).
    """

    path = Path(path)
    if path.is_symlink():
        raise ValueError(f"refusing to write through symlink: {path}")
    if path.exists():
        try:
            if path.read_text(encoding="utf-8") == content:
                return False
        except OSError:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".opencontext.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
    return True


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def merge_mcp_config_file(
    path: Path, servers: dict[str, Any], *, root_key: str = "mcpServers"
) -> bool:
    """Read a JSON MCP config (if any), merge servers under ``root_key``, write atomically."""

    existing: dict[str, Any] = {}
    path = Path(path)
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    merged = merge_mcp_servers(existing, servers, root_key=root_key)
    return write_text_atomic(path, json.dumps(merged, indent=2) + "\n")
