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


_ANALYZER_RISK_VOCAB = {"low", "medium", "high", "critical"}


def test_mcp_impact_risk_matches_analyzer_single_source(tmp_path: Path) -> None:
    """The MCP impact risk MUST be the analyzer's value, not a second vocabulary.

    The handler previously recomputed risk from caller+dependent counts alone with
    a divergent low/normal/high scale, ignoring the analyzer's blast-radius model.
    Pin true parity so the agent and the engine never disagree on risk.
    """
    runtime, _ = _runtime(tmp_path)
    server = MCPServer(db_path=runtime.storage_path / "context_graph.db", runtime=runtime)

    node_id = server._find_node("audit_login", None)
    assert node_id is not None
    analyzer_risk = server.impact.analyze(node_id, depth=2).risk_level

    out = server._handle_impact({"symbol": "audit_login"})
    assert out["risk_level"] == analyzer_risk
    assert out["risk_level"] in _ANALYZER_RISK_VOCAB  # never "normal", never "unknown"


def test_mcp_impact_risk_rises_with_callers(tmp_path: Path) -> None:
    """A symbol that is actually called crosses out of the trivial 'low' band.

    Exercises a non-trivial risk branch (the toy fixture's leaf symbol never
    could), proving the handler surfaces the analyzer's graduated levels.
    """
    project_root = tmp_path / "called"
    (project_root / "src").mkdir(parents=True)
    (project_root / "src" / "core.py").write_text(
        "\n".join(
            [
                "def target() -> int:",
                "    return 1",
                "",
                "def caller_a() -> int:",
                "    return target()",
                "",
                "def caller_b() -> int:",
                "    return target() + caller_a()",
            ]
        ),
        encoding="utf-8",
    )
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/called",
    )
    runtime.index_project(project_root)
    server = MCPServer(db_path=runtime.storage_path / "context_graph.db", runtime=runtime)

    out = server._handle_impact({"symbol": "target"})
    assert out["affected_nodes"] >= 1
    assert out["risk_level"] in _ANALYZER_RISK_VOCAB
    assert out["risk_level"] != "low"  # has real callers -> graduated above the floor


def test_mcp_node_carries_structured_symbol(tmp_path: Path) -> None:
    """opencontext_node returns a decodable structured symbol identity."""
    from opencontext_core.indexing.scip_symbol import parse_symbol

    runtime, _ = _runtime(tmp_path)
    server = MCPServer(db_path=runtime.storage_path / "context_graph.db", runtime=runtime)

    out = server._handle_node({"symbol": "audit_login"})
    assert "symbol" in out, "node output is missing the structured symbol"
    parsed = parse_symbol(out["symbol"])  # must round-trip, not be an opaque hash
    assert parsed.manager == "python"
    assert parsed.leaf == "audit_login"


def test_mcp_server_without_runtime_is_backward_compatible(tmp_path: Path) -> None:
    runtime, _ = _runtime(tmp_path)
    server = MCPServer(db_path=runtime.storage_path / "context_graph.db")  # no runtime
    out = server._handle_context({"task": "auth"})
    # Legacy shape still works (no gates), so existing integrations don't break.
    assert "context" in out
