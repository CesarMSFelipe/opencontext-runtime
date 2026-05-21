"""Tests for MCP stdio server."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from opencontext_core.mcp_stdio import MCPServer


class TestMCPServer:
    """Test MCP stdio server."""

    def test_initialization(self, tmp_path: Path) -> None:
        """Server initializes with correct tools."""

        server = MCPServer(db_path=tmp_path / "test.db")
        assert len(server.tools) == 8
        assert "opencontext_search" in server.tools
        assert "opencontext_context" in server.tools
        assert "opencontext_callers" in server.tools
        assert "opencontext_callees" in server.tools
        assert "opencontext_impact" in server.tools
        assert "opencontext_node" in server.tools
        assert "opencontext_files" in server.tools
        assert "opencontext_status" in server.tools
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
            assert len(result["tools"]) == 8
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
            assert "indexed" in result
        server.close()
