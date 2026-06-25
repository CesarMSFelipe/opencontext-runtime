"""Tests for MCP tool result envelope contracts in _call_tool.

Envelope coverage by path:
  - denied → ToolResultEnvelope (status=denied), backward-compat error/reason keys
  - unknown tool → ToolResultEnvelope (status=failed), backward-compat error key
  - exception → ToolResultEnvelope (status=failed), backward-compat error key
  - success → ToolResultEnvelope (status=passed), payload under data
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_server(allows: bool = True):
    from opencontext_core.mcp_stdio import MCPServer

    server = MCPServer.__new__(MCPServer)
    policy = MagicMock()
    policy.allows.return_value = allows
    server.policy = policy
    return server


def test_denied_tool_returns_envelope():
    server = _make_server(allows=False)
    result = server._call_tool("opencontext_search", {})

    assert result.get("schema_version") == "opencontext.mcp_tool_result.v1"
    assert result.get("status") == "denied"
    assert result.get("error") is not None


def test_unknown_tool_returns_envelope():
    server = _make_server()
    with patch.object(server, "_handlers", return_value={}):
        result = server._call_tool("nonexistent_tool", {})

    assert result.get("schema_version") == "opencontext.mcp_tool_result.v1"
    assert result.get("status") == "failed"
    assert result.get("error") is not None


def test_exception_returns_envelope():
    server = _make_server()

    def broken_handler(_params):
        raise ValueError("boom")

    with patch.object(server, "_handlers", return_value={"opencontext_search": broken_handler}):
        result = server._call_tool("opencontext_search", {})

    assert result.get("schema_version") == "opencontext.mcp_tool_result.v1"
    assert result.get("status") == "failed"
    assert result.get("error") == "boom"


def test_success_returns_envelope_with_data():
    server = _make_server()

    def fake_handler(_params):
        return {"items": [1, 2, 3], "count": 3}

    with patch.object(server, "_handlers", return_value={"opencontext_search": fake_handler}):
        result = server._call_tool("opencontext_search", {})

    assert result.get("schema_version") == "opencontext.mcp_tool_result.v1"
    assert result.get("status") == "passed"
    assert result.get("tool") == "opencontext_search"
    assert result.get("data") == {"items": [1, 2, 3], "count": 3}
    assert "error" not in result


def test_denied_has_backward_compat_error_key():
    server = _make_server(allows=False)
    result = server._call_tool("opencontext_search", {})
    # Backward compat: callers that check "error" in result still work.
    assert "error" in result
