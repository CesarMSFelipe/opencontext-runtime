"""`opencontext_node` with code=true returns the symbol's exact source — the one-call
surgical-locate that replaces 'search to find it, then Read the whole file'."""

from __future__ import annotations

from pathlib import Path


def _indexed_server(tmp_path: Path):
    from opencontext_core import mcp_stdio
    from opencontext_core.runtime import OpenContextRuntime

    proj = tmp_path / "proj"
    (proj / "pkg").mkdir(parents=True)
    (proj / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (proj / "pkg" / "core.py").write_text(
        'def widget(x, scale=1):\n    """Scale x."""\n    return x * scale\n',
        encoding="utf-8",
    )
    runtime = OpenContextRuntime(storage_path=proj / ".storage" / "opencontext")
    runtime.index_project(proj)
    db = proj / ".storage" / "opencontext" / "context_graph.db"
    return mcp_stdio.MCPServer(db_path=db, project_root=proj)


def test_node_code_true_returns_source(tmp_path: Path) -> None:
    server = _indexed_server(tmp_path)
    try:
        out = server._handle_node({"symbol": "widget", "code": True})
        assert out.get("name") == "widget"
        # The exact source (def..return) comes back in this one call — no file Read.
        assert "def widget(x, scale=1):" in out.get("code", "")
        assert "return x * scale" in out.get("code", "")
    finally:
        server.close()


def test_node_code_default_omits_source(tmp_path: Path) -> None:
    server = _indexed_server(tmp_path)
    try:
        out = server._handle_node({"symbol": "widget"})
        assert out.get("name") == "widget"
        assert "code" not in out  # body is opt-in, so the default response stays small
    finally:
        server.close()
