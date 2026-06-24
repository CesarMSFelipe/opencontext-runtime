"""Tests for per-tool MCP outputSchema in tools/list (Workstream C3)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.mcp_stdio import MCPServer, _tool_output_schema


def test_output_schema_is_permissive_object() -> None:
    schema = _tool_output_schema("opencontext_search")
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is True


def test_output_schema_documents_success_keys() -> None:
    schema = _tool_output_schema("opencontext_search")
    assert "results" in schema["properties"]


def test_output_schema_always_documents_envelope_keys() -> None:
    # Even a tool with no documented success keys carries the envelope/error keys.
    schema = _tool_output_schema("totally_unknown_tool")
    for key in ("schema_version", "tool", "status", "error", "reason", "policy", "warnings"):
        assert key in schema["properties"]


def test_output_schema_no_required_keys() -> None:
    # No key is required — success dicts and envelopes both validate.
    schema = _tool_output_schema("opencontext_run")
    assert "required" not in schema


def test_write_tool_output_schema_has_applied() -> None:
    schema = _tool_output_schema("opencontext_replace_symbol_body")
    assert "applied" in schema["properties"]


def _tools_list(server: MCPServer) -> list[dict]:
    """Drive a real tools/list request and capture the response."""
    captured: dict = {}

    def _fake_send(request_id, result):  # type: ignore[no-untyped-def]
        captured["result"] = result

    server._send_response = _fake_send  # type: ignore[method-assign]
    server._handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    return captured["result"]["tools"]


def test_tools_list_includes_output_schema(tmp_path: Path) -> None:
    server = MCPServer(db_path=tmp_path / "g.db")
    tools = _tools_list(server)
    assert tools
    for tool in tools:
        assert "outputSchema" in tool, f"{tool['name']} missing outputSchema"
        assert tool["outputSchema"]["type"] == "object"
    server.close()


def test_tools_list_still_has_input_schema(tmp_path: Path) -> None:
    server = MCPServer(db_path=tmp_path / "g.db")
    tools = _tools_list(server)
    for tool in tools:
        assert "inputSchema" in tool
    server.close()
