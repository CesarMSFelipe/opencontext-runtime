"""Tests for MCP stdio server."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from opencontext_core.mcp_stdio import MCPServer, _compute_max_nodes, _to_tool_result


def test_tool_result_envelope_redacts_secrets() -> None:
    secret = "AKIAIOSFODNN7EXAMPLE"  # canonical AWS access-key shape
    envelope = _to_tool_result({"results": [{"snippet": f"aws_key = {secret}"}]})
    assert secret not in envelope["content"][0]["text"]
    assert secret not in json.dumps(envelope["structuredContent"])
    assert envelope["isError"] is False


class TestAdaptiveScaling:
    """Test adaptive max_nodes scaling."""

    def test_tier_below_500(self) -> None:
        assert _compute_max_nodes(0) == 10
        assert _compute_max_nodes(100) == 10
        assert _compute_max_nodes(499) == 10

    def test_tier_500_to_1999(self) -> None:
        assert _compute_max_nodes(500) == 20
        assert _compute_max_nodes(1500) == 20
        assert _compute_max_nodes(1999) == 20

    def test_tier_2000_to_9999(self) -> None:
        assert _compute_max_nodes(2000) == 40
        assert _compute_max_nodes(5000) == 40
        assert _compute_max_nodes(9999) == 40

    def test_tier_10000_to_24999(self) -> None:
        assert _compute_max_nodes(10000) == 50
        assert _compute_max_nodes(20000) == 50
        assert _compute_max_nodes(24999) == 50

    def test_tier_25000_and_above(self) -> None:
        assert _compute_max_nodes(25000) == 60
        assert _compute_max_nodes(100000) == 60


class TestTraceTool:
    """Test the opencontext_trace tool."""

    def test_trace_tool_registered(self, tmp_path: Path) -> None:
        """opencontext_trace appears in tool list."""
        server = MCPServer(db_path=tmp_path / "test.db")
        assert "opencontext_trace" in server.tools
        assert (
            server.tools["opencontext_trace"]["description"]
            == "Find the shortest path between two symbols in the call graph"
        )
        server.close()

    def test_trace_symbol_not_found(self, tmp_path: Path) -> None:
        """Missing symbol returns error."""
        server = MCPServer(db_path=tmp_path / "test.db")
        result = server._call_tool(
            "opencontext_trace",
            {
                "source": "nonexistent",
                "target": "main",
            },
        )
        assert "error" in result
        assert "SYMBOL_NOT_FOUND" in result.get("code", "")
        server.close()

    def test_trace_requires_both_params(self, tmp_path: Path) -> None:
        """Missing source or target returns error."""
        server = MCPServer(db_path=tmp_path / "test.db")
        result = server._call_tool("opencontext_trace", {"source": "main"})
        assert "error" in result
        server.close()


class TestMCPServer:
    """Test MCP stdio server."""

    def test_initialization(self, tmp_path: Path) -> None:
        """Server initializes with correct tools."""

        server = MCPServer(db_path=tmp_path / "test.db")
        assert len(server.tools) == 14
        assert "opencontext_search" in server.tools
        assert "opencontext_context" in server.tools
        assert "opencontext_callers" in server.tools
        assert "opencontext_callees" in server.tools
        assert "opencontext_impact" in server.tools
        assert "opencontext_node" in server.tools
        assert "opencontext_files" in server.tools
        assert "opencontext_status" in server.tools
        assert "opencontext_trace" in server.tools
        assert "opencontext_replace_symbol_body" in server.tools
        assert "opencontext_insert_before_symbol" in server.tools
        assert "opencontext_insert_after_symbol" in server.tools
        assert "opencontext_rename_symbol" in server.tools
        server.close()

    def test_handle_initialize(self, tmp_path: Path) -> None:
        """Handle initialize request."""

        server = MCPServer(db_path=tmp_path / "test.db")
        request = {"id": 1, "method": "initialize", "params": {}}
        with patch.object(server, "_send_response") as mock_send:
            server._handle_request(request)
            mock_send.assert_called_once()
            response = mock_send.call_args[0][1]
            assert response["protocolVersion"] == "2024-11-05"
            assert response["serverInfo"]["name"] == "opencontext-mcp"
        server.close()

    def test_handle_tools_list(self, tmp_path: Path) -> None:
        """Handle tools/list request."""

        server = MCPServer(db_path=tmp_path / "test.db")
        request = {"id": 1, "method": "tools/list", "params": {}}
        with patch.object(server, "_send_response") as mock_send:
            server._handle_request(request)
            mock_send.assert_called_once()
            result = mock_send.call_args[0][1]
            assert len(result["tools"]) == 14
            assert all("name" in t for t in result["tools"])
            assert all("description" in t for t in result["tools"])
        server.close()

    def test_handle_unknown_method(self, tmp_path: Path) -> None:
        """Handle unknown method returns error."""

        server = MCPServer(db_path=tmp_path / "test.db")
        request = {"id": 1, "method": "unknown", "params": {}}
        with patch.object(server, "_send_error") as mock_send:
            server._handle_request(request)
            mock_send.assert_called_once()
            assert mock_send.call_args[0][1] == -32601
        server.close()

    def test_call_tool_unknown(self, tmp_path: Path) -> None:
        """Call unknown tool returns error."""

        server = MCPServer(db_path=tmp_path / "test.db")
        result = server._call_tool("unknown_tool", {})
        assert "error" in result
        server.close()

    def test_status_tool_empty_db(self, tmp_path: Path) -> None:
        """Status tool on empty database."""

        server = MCPServer(db_path=tmp_path / "test.db")
        result = server._call_tool("opencontext_status", {})
        assert result["indexed"] is False
        assert result["nodes"] == 0
        assert result["edges"] == 0
        server.close()

    def test_explicit_max_nodes_is_honored(self, tmp_path: Path) -> None:
        """An explicit max_nodes (even 20) must not be overridden by adaptive scaling."""
        server = MCPServer(db_path=tmp_path / "test.db")
        server.runtime = None  # force the adaptive (non-verified) context path
        captured: dict[str, object] = {}

        def _fake_build(**kwargs: object) -> object:
            captured.update(kwargs)
            return object()

        server.context_builder.build_context = _fake_build  # type: ignore[method-assign]
        server.context_builder.render = lambda context: "x"  # type: ignore[method-assign]
        server._call_tool("opencontext_context", {"task": "t", "max_nodes": 20})
        assert captured["max_nodes"] == 20
        server.close()

    def test_tools_call_method(self, tmp_path: Path) -> None:
        """Handle tools/call request."""

        server = MCPServer(db_path=tmp_path / "test.db")
        request = {
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "opencontext_status",
                "arguments": {},
            },
        }
        with patch.object(server, "_send_response") as mock_send:
            server._handle_request(request)
            mock_send.assert_called_once()
            result = mock_send.call_args[0][1]
            # MCP tools/call envelope: a content array plus structured payload.
            assert result["content"][0]["type"] == "text"
            assert result["isError"] is False
            assert "indexed" in result["structuredContent"]
        server.close()

    def test_notifications_initialized_gets_no_response(self, tmp_path: Path) -> None:
        """A JSON-RPC notification must never be answered."""

        server = MCPServer(db_path=tmp_path / "test.db")
        request = {"method": "notifications/initialized"}
        with patch.object(server, "_send_response") as resp, patch.object(
            server, "_send_error"
        ) as err:
            server._handle_request(request)
            resp.assert_not_called()
            err.assert_not_called()
        server.close()

    def test_ping_returns_empty_result(self, tmp_path: Path) -> None:
        server = MCPServer(db_path=tmp_path / "test.db")
        request = {"id": 7, "method": "ping", "params": {}}
        with patch.object(server, "_send_response") as resp:
            server._handle_request(request)
            resp.assert_called_once()
            assert resp.call_args[0][0] == 7
            assert resp.call_args[0][1] == {}
        server.close()


class TestMCPPolicyEnforcement:
    """Regression tests: every MCP tool must route through ToolPermissionPolicy.

    Slice 0 (mcp-policy-hotfix). Closes the bypass where ``_call_tool`` ran
    handlers without checking the policy. Every MCP tool is covered by the
    same gate so no tool executes without a prior policy check.
    """

    def test_default_policy_allows_registered_tools(self, tmp_path: Path) -> None:
        """The default policy allows every tool that the server actually exposes."""

        from opencontext_core.tools.policy import ToolPermissionPolicy

        server = MCPServer(db_path=tmp_path / "test.db")
        default_policy = ToolPermissionPolicy(
            allowed_tools=set(server.tools.keys()),
        )
        server.policy = default_policy
        result = server._call_tool("opencontext_status", {})
        assert "error" not in result or "denied" not in result.get("error", "").lower()
        assert result.get("indexed") is False
        server.close()

    def test_unapproved_tool_is_denied_before_execution(self, tmp_path: Path) -> None:
        """A tool that is not in the allowlist is denied without invoking the handler."""

        from opencontext_core.tools.policy import ToolPermissionPolicy

        server = MCPServer(db_path=tmp_path / "test.db")
        # Empty allowlist -> nothing is allowed.
        server.policy = ToolPermissionPolicy(allowed_tools=set())

        with patch.object(server, "_handle_status") as mock_status:
            result = server._call_tool("opencontext_status", {})

        assert "error" in result
        assert "denied" in result["error"].lower()
        # Crucially: the handler must not have run.
        mock_status.assert_not_called()
        server.close()

    def test_unknown_tool_still_rejected(self, tmp_path: Path) -> None:
        """An unknown tool name is still rejected after the policy gate."""

        from opencontext_core.tools.policy import ToolPermissionPolicy

        server = MCPServer(db_path=tmp_path / "test.db")
        server.policy = ToolPermissionPolicy(allowed_tools=set(server.tools.keys()))

        result = server._call_tool("definitely_not_a_tool", {})
        assert "error" in result
        server.close()

    def test_denied_tool_decision_recorded(self, tmp_path: Path) -> None:
        """The denial result includes the policy reason for observability."""

        from opencontext_core.tools.policy import ToolPermissionPolicy

        server = MCPServer(db_path=tmp_path / "test.db")
        server.policy = ToolPermissionPolicy(allowed_tools={"opencontext_status"})

        result = server._call_tool("opencontext_search", {"query": "x"})
        assert "error" in result
        assert "opencontext_search" in result["error"]
        assert "reason" in result
        server.close()

    def test_all_tools_routed_through_policy(self, tmp_path: Path) -> None:
        """Every registered tool name must hit the policy gate."""

        from opencontext_core.tools.policy import ToolPermissionPolicy

        server = MCPServer(db_path=tmp_path / "test.db")
        # Allow only one tool; every other registered tool must be denied.
        server.policy = ToolPermissionPolicy(allowed_tools={"opencontext_status"})

        denied = []
        for tool_name in server.tools:
            if tool_name == "opencontext_status":
                continue
            result = server._call_tool(tool_name, {})
            if "denied" in result.get("error", "").lower():
                denied.append(tool_name)

        assert len(denied) == len(server.tools) - 1
        assert set(denied) == set(server.tools) - {"opencontext_status"}
        server.close()
