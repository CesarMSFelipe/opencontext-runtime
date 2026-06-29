"""PR-013 SPEC-CLI-013-16: MCP workflow/profile/doctor meta tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.mcp_stdio import MCPServer

_META_TOOLS = {
    "opencontext_workflow_list",
    "opencontext_workflow_explain",
    "opencontext_profile_list",
    "opencontext_profile_explain",
    "opencontext_doctor",
}


@pytest.fixture
def server(tmp_path: Path) -> MCPServer:
    # Meta tools are read-only and safe by default — no policy override needed.
    return MCPServer(db_path=tmp_path / "kg.db")


def test_meta_tools_registered_and_in_default(server: MCPServer) -> None:
    assert _META_TOOLS <= set(server.tools)
    assert _META_TOOLS <= set(server._handlers())
    assert _META_TOOLS <= set(server._default_tool_names())


def test_workflow_list_and_explain(server: MCPServer) -> None:
    listed = server._call_tool("opencontext_workflow_list", {})
    assert listed["status"] == "passed"
    assert listed["data"]["workflows"]

    explained = server._call_tool("opencontext_workflow_explain", {"workflow": "sdd"})
    assert explained["status"] == "passed"
    assert explained["data"]["phases"]


def test_profile_list_and_explain(server: MCPServer) -> None:
    listed = server._call_tool("opencontext_profile_list", {})
    assert listed["data"]["config_profiles"]
    assert listed["data"]["model_profiles"]

    explained = server._call_tool("opencontext_profile_explain", {"profile": "enterprise"})
    assert explained["data"]["family"] == "config"


def test_doctor_tool(server: MCPServer, tmp_path: Path) -> None:
    out = server._call_tool("opencontext_doctor", {"root": str(tmp_path)})
    assert out["status"] == "passed"
    assert "findings" in out["data"]
