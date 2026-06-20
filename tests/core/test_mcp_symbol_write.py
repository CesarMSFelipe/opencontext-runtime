"""Tests for symbol-level write tools on the MCP stdio server.

These tools edit source files precisely against the knowledge graph: the symbol
is resolved to its file + line span via the graph, and the edit is applied with
the atomic write primitive. Every write is gated by the same tool-permission
policy as the read tools and returns a structured, traceable result.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
from opencontext_core.mcp_stdio import MCPServer
from opencontext_core.tools.policy import ToolPermissionPolicy

AUTH_SOURCE = "\n".join(
    [
        "class AuthService:",
        "    def login(self, username: str) -> bool:",
        "        checked = bool(username)",
        "        return checked",
        "",
        "def audit_login(username: str) -> str:",
        "    return username",
        "",
        "def caller():",
        "    return audit_login('x')",
        "",
    ]
)


@pytest.fixture
def indexed_project(tmp_path: Path) -> tuple[MCPServer, Path]:
    """A tiny indexed project plus an MCP server rooted at it.

    Yields the server and the project root. The knowledge graph is indexed and
    closed before the server opens so the server reads the committed graph.
    """

    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "auth.py").write_text(AUTH_SOURCE, encoding="utf-8")

    config = KnowledgeGraphConfig(enabled=True, languages=["python"])
    kg = KnowledgeGraph(config=config, db_path=tmp_path / "kg.db")
    kg.index_project(root)
    kg.close()

    server = MCPServer(db_path=tmp_path / "kg.db", project_root=root)
    yield server, root
    server.close()


def _read(root: Path) -> str:
    return (root / "src" / "auth.py").read_text(encoding="utf-8")


class TestRegistration:
    def test_write_tools_registered(self, tmp_path: Path) -> None:
        server = MCPServer(db_path=tmp_path / "test.db")
        for name in (
            "opencontext_replace_symbol_body",
            "opencontext_insert_before_symbol",
            "opencontext_insert_after_symbol",
            "opencontext_rename_symbol",
        ):
            assert name in server.tools
            assert name in server._default_tool_names()
            assert name in server._handlers()
        server.close()


class TestReplaceSymbolBody:
    def test_replaces_only_target_span(self, indexed_project: tuple[MCPServer, Path]) -> None:
        server, root = indexed_project
        new_body = "\n".join(
            [
                "def audit_login(username: str) -> str:",
                "    return username.upper()",
            ]
        )
        result = server._call_tool(
            "opencontext_replace_symbol_body",
            {"symbol": "audit_login", "file": "src/auth.py", "body": new_body},
        )

        assert result["applied"] is True
        assert result["symbol"] == "audit_login"
        assert result["file"] == "src/auth.py"
        assert "error" not in result
        # Changed range covers the original span of audit_login (lines 6-7).
        assert result["changed_range"] == {"start_line": 6, "end_line": 7}

        text = _read(root)
        assert "return username.upper()" in text
        # The other symbols are untouched.
        assert "class AuthService:" in text
        assert "checked = bool(username)" in text
        assert "return audit_login('x')" in text
        # No duplication of the replaced symbol.
        assert text.count("def audit_login(") == 1

    def test_unresolved_symbol_returns_error(self, indexed_project: tuple[MCPServer, Path]) -> None:
        server, root = indexed_project
        before = _read(root)
        result = server._call_tool(
            "opencontext_replace_symbol_body",
            {"symbol": "does_not_exist", "body": "x = 1"},
        )
        assert "error" in result
        assert result.get("applied") is False
        # File is left completely intact.
        assert _read(root) == before

    def test_rejects_edit_that_breaks_python(self, indexed_project: tuple[MCPServer, Path]) -> None:
        # Fail closed: an edit that leaves the file syntactically invalid (here an
        # unclosed paren) must be rejected and the file left intact, not written.
        server, root = indexed_project
        before = _read(root)
        result = server._call_tool(
            "opencontext_replace_symbol_body",
            {"symbol": "audit_login", "file": "src/auth.py", "body": "def audit_login(:"},
        )
        assert result.get("applied") is False
        assert "invalid Python" in result.get("error", "")
        assert "hint" in result  # points the agent at passing the full definition
        assert _read(root) == before  # nothing written


class TestInsertBeforeSymbol:
    def test_inserts_code_above_symbol(self, indexed_project: tuple[MCPServer, Path]) -> None:
        server, root = indexed_project
        result = server._call_tool(
            "opencontext_insert_before_symbol",
            {
                "symbol": "audit_login",
                "file": "src/auth.py",
                "content": "# audit helper below",
            },
        )
        assert result["applied"] is True
        assert "error" not in result

        lines = _read(root).splitlines()
        idx = lines.index("# audit helper below")
        # The inserted line sits immediately before the def line.
        assert lines[idx + 1] == "def audit_login(username: str) -> str:"


class TestInsertAfterSymbol:
    def test_inserts_code_below_symbol(self, indexed_project: tuple[MCPServer, Path]) -> None:
        server, root = indexed_project
        result = server._call_tool(
            "opencontext_insert_after_symbol",
            {
                "symbol": "audit_login",
                "file": "src/auth.py",
                "content": "# end of audit_login",
            },
        )
        assert result["applied"] is True
        assert "error" not in result

        lines = _read(root).splitlines()
        idx = lines.index("# end of audit_login")
        # The line right above the marker is the last line of audit_login's body.
        assert lines[idx - 1] == "    return username"


class TestRenameSymbol:
    def test_renames_definition_and_known_reference(
        self, indexed_project: tuple[MCPServer, Path]
    ) -> None:
        server, root = indexed_project
        result = server._call_tool(
            "opencontext_rename_symbol",
            {
                "symbol": "audit_login",
                "file": "src/auth.py",
                "new_name": "record_login",
            },
        )
        assert result["applied"] is True
        assert result["symbol"] == "audit_login"
        assert result["new_name"] == "record_login"
        assert "error" not in result

        text = _read(root)
        # Definition renamed.
        assert "def record_login(username: str) -> str:" in text
        assert "def audit_login(" not in text
        # Known reference (call site) updated.
        assert "return record_login('x')" in text
        assert "audit_login" not in text

    def test_rename_requires_new_name(self, indexed_project: tuple[MCPServer, Path]) -> None:
        server, root = indexed_project
        before = _read(root)
        result = server._call_tool(
            "opencontext_rename_symbol",
            {"symbol": "audit_login", "file": "src/auth.py"},
        )
        assert "error" in result
        assert result.get("applied") is False
        assert _read(root) == before

    def test_rename_rejects_python_keyword(self, indexed_project: tuple[MCPServer, Path]) -> None:
        # 'class' passes str.isidentifier() but renaming to it would break syntax.
        server, root = indexed_project
        before = _read(root)
        result = server._call_tool(
            "opencontext_rename_symbol",
            {"symbol": "audit_login", "file": "src/auth.py", "new_name": "class"},
        )
        assert result.get("applied") is False
        assert "keyword" in result.get("error", "")
        assert _read(root) == before

    def test_rename_unresolved_symbol_returns_error(
        self, indexed_project: tuple[MCPServer, Path]
    ) -> None:
        server, root = indexed_project
        before = _read(root)
        result = server._call_tool(
            "opencontext_rename_symbol",
            {"symbol": "ghost", "new_name": "spirit"},
        )
        assert "error" in result
        assert result.get("applied") is False
        assert _read(root) == before


class TestWritePolicyGate:
    def test_write_tool_denied_when_not_allowlisted(
        self, indexed_project: tuple[MCPServer, Path]
    ) -> None:
        server, root = indexed_project
        before = _read(root)
        # Allowlist excludes the write tool entirely.
        server.policy = ToolPermissionPolicy(allowed_tools={"opencontext_status"})
        result = server._call_tool(
            "opencontext_replace_symbol_body",
            {"symbol": "audit_login", "file": "src/auth.py", "body": "x = 1"},
        )
        assert "error" in result
        assert "denied" in result["error"].lower()
        # The denied call must not have edited the file.
        assert _read(root) == before
