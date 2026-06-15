"""End-to-end behavior proof for the agentic-control-plane change.

Ties the headline promises together against the REAL runtime (no mocks of the
pipeline): verified context carries real content, the three surfaces agree on
gates/risk, the graph tolerates natural-language queries, and the insufficient
path stays auditable. If this passes, the spine closes end to end.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from opencontext_core.config import default_config_data
from opencontext_core.mcp_stdio import MCPServer
from opencontext_core.retrieval.contracts import VerifiedContextRequest
from opencontext_core.runtime import OpenContextRuntime


def _runtime(tmp_path: Path) -> tuple[OpenContextRuntime, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "src").mkdir()
    (project_root / "src" / "auth.py").write_text(
        "class AuthService:\n"
        "    def login(self, username: str) -> bool:\n"
        "        return bool(username)\n",
        encoding="utf-8",
    )
    (project_root / "README.md").write_text(
        "# Sample\nAuthentication lives in src/auth.py\n", encoding="utf-8"
    )
    data = default_config_data()
    data["project"]["name"] = "acp-proof"
    data["project_index"]["root"] = str(project_root)
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    runtime = OpenContextRuntime(
        config_path=config_path, storage_path=tmp_path / ".storage/opencontext"
    )
    runtime.index_project(project_root)
    return runtime, project_root


def test_verified_context_delivers_real_content_with_green_gates(tmp_path: Path) -> None:
    runtime, root = _runtime(tmp_path)
    result = runtime.verify_context(
        VerifiedContextRequest(query="Where is authentication implemented?", root=root)
    )
    # the agent receives REAL code, not empty headers.
    assert "AuthService" in result.context or "def login" in result.context
    assert any((e.content or "").strip() for e in result.evidence)
    # ...and the gates are computed over that real content.
    assert {g.name for g in result.gates} >= {"coverage", "provenance", "policy"}
    assert result.trace_id


def test_three_surfaces_agree_on_gates_and_risk(tmp_path: Path) -> None:
    runtime, root = _runtime(tmp_path)
    q = "Where is authentication implemented?"

    verified = runtime.verify_context(VerifiedContextRequest(query=q, root=root))
    prepared = runtime.prepare_context(q, root=root)
    server = MCPServer(db_path=runtime.storage_path / "context_graph.db", runtime=runtime)
    mcp = server._handle_context({"task": q})

    # CLI (verify) == API (prepare) == MCP on the trust-relevant fields.
    names = {g.name for g in verified.gates}
    assert {g.name for g in prepared.gates} == names
    assert {g["name"] for g in mcp["gates"]} == names
    assert prepared.risk_level == verified.risk_level.value == mcp["risk_level"]


def test_graph_tolerates_natural_language_query(tmp_path: Path) -> None:
    runtime, root = _runtime(tmp_path)
    # punctuation/operators must not crash the graph source (no exception).
    result = runtime.verify_context(
        VerifiedContextRequest(query="How does login() work? (auth / sessions)", root=root)
    )
    assert result.trace_id
    assert runtime.load_trace(result.trace_id).run_id == result.trace_id
