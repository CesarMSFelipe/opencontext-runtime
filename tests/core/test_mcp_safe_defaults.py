"""Tests: code-write tools and opencontext_run are NOT in the safe default allowlist."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.mcp_stdio import MCPServer

_WRITE_TOOLS = {
    "opencontext_replace_symbol_body",
    "opencontext_insert_before_symbol",
    "opencontext_insert_after_symbol",
    "opencontext_rename_symbol",
    "opencontext_run",
}

_READ_TOOLS = {
    "opencontext_search",
    "opencontext_context",
    "opencontext_callers",
    "opencontext_callees",
    "opencontext_impact",
    "opencontext_node",
    "opencontext_files",
    "opencontext_status",
    "opencontext_trace",
    "opencontext_quality",
    "opencontext_memory_search",
    "opencontext_memory_context",
}


def test_write_tools_not_in_default_allowlist(tmp_path: Path) -> None:
    server = MCPServer(db_path=tmp_path / "test.db")
    defaults = set(server._default_tool_names())
    for tool in _WRITE_TOOLS:
        assert tool not in defaults, f"{tool} should not be in safe default allowlist"
    server.close()


def test_read_tools_in_default_allowlist(tmp_path: Path) -> None:
    server = MCPServer(db_path=tmp_path / "test.db")
    defaults = set(server._default_tool_names())
    for tool in _READ_TOOLS:
        assert tool in defaults, f"{tool} missing from safe default allowlist"
    server.close()


def test_write_tool_denied_without_explicit_policy(tmp_path: Path) -> None:
    server = MCPServer(db_path=tmp_path / "test.db")
    result = server._call_tool("opencontext_replace_symbol_body", {})
    assert "error" in result
    assert "denied" in result["error"].lower()
    server.close()


def test_run_tool_denied_without_explicit_policy(tmp_path: Path) -> None:
    server = MCPServer(db_path=tmp_path / "test.db")
    result = server._call_tool("opencontext_run", {})
    assert "error" in result
    assert "denied" in result["error"].lower()
    server.close()


def test_write_tool_denied_result_has_envelope_fields(tmp_path: Path) -> None:
    server = MCPServer(db_path=tmp_path / "test.db")
    result = server._call_tool("opencontext_replace_symbol_body", {})
    assert result.get("status") == "denied"
    assert result.get("tool") == "opencontext_replace_symbol_body"
    assert result.get("schema_version") == "opencontext.mcp_tool_result.v1"
    server.close()


def test_write_tools_still_registered_in_tools_dict(tmp_path: Path) -> None:
    """Write tools appear in server.tools (for tools/list) but not the default allowlist."""
    server = MCPServer(db_path=tmp_path / "test.db")
    for tool in _WRITE_TOOLS:
        assert tool in server.tools, f"{tool} missing from server.tools"
    server.close()


def test_memory_write_tools_in_default_allowlist(tmp_path: Path) -> None:
    """memory_save and memory_judge ARE in the safe default (lightweight, agent-loop needed)."""
    server = MCPServer(db_path=tmp_path / "test.db")
    defaults = set(server._default_tool_names())
    assert "opencontext_memory_save" in defaults
    assert "opencontext_memory_judge" in defaults
    server.close()
