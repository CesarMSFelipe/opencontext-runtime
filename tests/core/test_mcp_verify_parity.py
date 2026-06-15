"""the launched MCP server must route through verify_context.

Before the fix, mcp_stdio handlers returned raw ungated context (no gates/trust/
trace) and opencontext_impact hardcoded risk_level='unknown'. The agent's primary
surface had no audit trail. This pins parity with runtime.verify_context.
"""

from __future__ import annotations

from pathlib import Path

from conftest import create_sample_project, write_config

from opencontext_core.mcp_stdio import MCPServer
from opencontext_core.retrieval.contracts import VerifiedContextRequest
from opencontext_core.runtime import OpenContextRuntime


def _runtime(tmp_path: Path) -> tuple[OpenContextRuntime, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/opencontext",
    )
    runtime.index_project(project_root)
    return runtime, project_root


def test_mcp_context_routes_through_verify_context(tmp_path: Path) -> None:
    runtime, project_root = _runtime(tmp_path)
    server = MCPServer(db_path=runtime.storage_path / "context_graph.db", runtime=runtime)

    out = server._handle_context({"task": "Where is authentication implemented?"})

    # The MCP context response now carries the verification fields.
    assert "gates" in out and "risk_level" in out and "trace_id" in out
    assert out["trace_id"]
    verified = runtime.verify_context(
        VerifiedContextRequest(query="Where is authentication implemented?", root=project_root)
    )
    assert {g["name"] for g in out["gates"]} == {g.name for g in verified.gates}
    assert out["risk_level"] == verified.risk_level.value


def test_mcp_impact_returns_real_risk_level(tmp_path: Path) -> None:
    runtime, _ = _runtime(tmp_path)
    server = MCPServer(db_path=runtime.storage_path / "context_graph.db", runtime=runtime)

    out = server._handle_impact({"symbol": "audit_login"})
    # Either the symbol resolves (real risk) or it is a clean not-found error —
    # but it MUST NOT report the hardcoded "unknown".
    if "risk_level" in out:
        assert out["risk_level"] in {"low", "normal", "high"}
        assert out["risk_level"] != "unknown"


def test_mcp_server_without_runtime_is_backward_compatible(tmp_path: Path) -> None:
    runtime, _ = _runtime(tmp_path)
    server = MCPServer(db_path=runtime.storage_path / "context_graph.db")  # no runtime
    out = server._handle_context({"task": "auth"})
    # Legacy shape still works (no gates), so existing integrations don't break.
    assert "context" in out
