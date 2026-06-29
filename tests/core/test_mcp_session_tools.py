"""PR-013 SPEC-CLI-013-16: MCP session_* step tools registered + governed."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.mcp_stdio import MCPServer
from opencontext_core.tools.policy import ToolPermissionPolicy

_SESSION_TOOLS = {
    "opencontext_session_start",
    "opencontext_session_next",
    "opencontext_session_observe",
    "opencontext_session_apply",
    "opencontext_session_inspect",
    "opencontext_session_status",
    "opencontext_session_resume",
    "opencontext_session_archive",
}


@pytest.fixture
def server(tmp_path: Path) -> MCPServer:
    s = MCPServer(db_path=tmp_path / "kg.db")
    s.policy = ToolPermissionPolicy(allowed_tools=set(s.tools.keys()))
    return s


def test_session_tools_registered(server: MCPServer) -> None:
    assert _SESSION_TOOLS <= set(server.tools)
    assert _SESSION_TOOLS <= set(server._handlers())


def test_start_then_next_advances(server: MCPServer, tmp_path: Path) -> None:
    start = server._call_tool(
        "opencontext_session_start", {"task": "x", "root": str(tmp_path)}
    )
    assert start["status"] == "passed"
    sid = start["data"]["session_id"]
    assert sid.startswith("sess-")

    nxt = server._call_tool(
        "opencontext_session_next", {"session_id": sid, "root": str(tmp_path)}
    )
    assert nxt["status"] == "passed"
    assert "kind" in nxt["data"]


def test_session_tools_governed_by_policy(tmp_path: Path) -> None:
    # Mutating session tools are NOT in the safe default allowlist; denied without opt-in.
    server = MCPServer(db_path=tmp_path / "kg.db")
    out = server._call_tool("opencontext_session_start", {"task": "x"})
    assert "error" in out
    assert "denied" in out["error"].lower()


def test_session_inspect_in_safe_default(tmp_path: Path) -> None:
    # Read-only session inspect/status ARE safe by default.
    server = MCPServer(db_path=tmp_path / "kg.db")
    defaults = set(server._default_tool_names())
    assert "opencontext_session_inspect" in defaults
    assert "opencontext_session_status" in defaults
