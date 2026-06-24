"""Tests for the MCP write-approval gate (C2) on symbol-edit write tools.

Workstream C2 of ``oc-memory-parity-and-polish`` (decision RD4):

- ``mcp.require_write_approval`` (bool, default ``False``) preserves today's
  behavior exactly (C2-1a).
- When ``True``, the four symbol-edit writers
  (``replace_symbol_body``/``insert_before_symbol``/``insert_after_symbol``/
  ``rename_symbol``) route through the existing
  ``ApprovalRequiredForWritesGate`` BEFORE any disk write: an unapproved call
  writes nothing and returns a structured "approval required" result (C2-2a);
  an approved call writes as today (C2-2b).
- Read tools and the agent memory tools (which target the store, not disk) are
  unaffected (C2-2c).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from opencontext_core.config import KnowledgeGraphConfig, McpToolsConfig, default_config_data
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
from opencontext_core.mcp_stdio import MCPServer

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


class _FakeRuntime:
    """Minimal runtime stand-in exposing only what the gate path reads.

    The MCP server reads ``runtime.config.tools.mcp.require_write_approval`` and
    resolves write paths under ``runtime.config.project_index.root``. A real
    ``OpenContextConfig`` is built from defaults so both attribute chains exist.
    """

    def __init__(self, root: Path, *, require_write_approval: bool) -> None:
        from opencontext_core.config import OpenContextConfig

        data = default_config_data()
        data["project"]["name"] = "c2-gate"
        data["project_index"]["root"] = str(root)
        data["tools"]["mcp"]["require_write_approval"] = require_write_approval
        self.config = OpenContextConfig.model_validate(data)
        # Memory tools resolve _v2_memory_store via getattr; absent here.


def _make_server(tmp_path: Path, *, require_write_approval: bool | None) -> tuple[MCPServer, Path]:
    """Index a tiny project and open a server over it.

    ``require_write_approval=None`` -> no runtime attached (legacy default path).
    Otherwise a fake runtime carries the toggle.
    """

    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "auth.py").write_text(AUTH_SOURCE, encoding="utf-8")

    config = KnowledgeGraphConfig(enabled=True, languages=["python"])
    kg = KnowledgeGraph(config=config, db_path=tmp_path / "kg.db")
    kg.index_project(root)
    kg.close()

    runtime: Any = None
    if require_write_approval is not None:
        runtime = _FakeRuntime(root, require_write_approval=require_write_approval)
    server = MCPServer(db_path=tmp_path / "kg.db", project_root=root, runtime=runtime)
    # NOTE: write-tool tests need explicit policy; code-write tools not in safe default
    from opencontext_core.tools.policy import ToolPermissionPolicy
    server.policy = ToolPermissionPolicy(allowed_tools=set(server.tools.keys()))
    return server, root


def _read(root: Path) -> str:
    return (root / "src" / "auth.py").read_text(encoding="utf-8")


class TestConfig:
    def test_require_write_approval_default_false(self) -> None:
        """C2-1a config: the toggle defaults to False."""

        assert McpToolsConfig().require_write_approval is False

    def test_root_config_default_false(self) -> None:
        """A default-loaded root config has the toggle False."""

        from opencontext_core.config import OpenContextConfig

        cfg = OpenContextConfig.model_validate(default_config_data())
        assert cfg.tools.mcp.require_write_approval is False


class TestDefaultOffPreservesBehavior:
    def test_no_runtime_writes_as_today(self, tmp_path: Path) -> None:
        """C2-1a: with no runtime (no config), writes apply exactly as today."""

        server, root = _make_server(tmp_path, require_write_approval=None)
        result = server._call_tool(
            "opencontext_replace_symbol_body",
            {
                "symbol": "audit_login",
                "file": "src/auth.py",
                "body": "def audit_login(username: str) -> str:\n    return username.upper()",
            },
        )
        assert result["data"]["applied"] is True
        assert "approval_required" not in result["data"]
        assert "return username.upper()" in _read(root)
        server.close()

    def test_flag_false_writes_as_today(self, tmp_path: Path) -> None:
        """C2-1a: require_write_approval=False is byte-identical to today."""

        server, root = _make_server(tmp_path, require_write_approval=False)
        result = server._call_tool(
            "opencontext_replace_symbol_body",
            {
                "symbol": "audit_login",
                "file": "src/auth.py",
                "body": "def audit_login(username: str) -> str:\n    return username.upper()",
            },
        )
        assert result["data"]["applied"] is True
        assert "approval_required" not in result["data"]
        assert "return username.upper()" in _read(root)
        server.close()


class TestGateBlocksUnapproved:
    @pytest.mark.parametrize(
        ("tool", "params"),
        [
            (
                "opencontext_replace_symbol_body",
                {"symbol": "audit_login", "file": "src/auth.py", "body": "def audit_login(): pass"},
            ),
            (
                "opencontext_insert_before_symbol",
                {"symbol": "audit_login", "file": "src/auth.py", "content": "# before\n"},
            ),
            (
                "opencontext_insert_after_symbol",
                {"symbol": "audit_login", "file": "src/auth.py", "content": "# after\n"},
            ),
            (
                "opencontext_rename_symbol",
                {"symbol": "audit_login", "file": "src/auth.py", "new_name": "audit_login_v2"},
            ),
        ],
    )
    def test_unapproved_write_is_blocked(
        self, tmp_path: Path, tool: str, params: dict[str, Any]
    ) -> None:
        """C2-2a: on + unapproved -> no file written, structured denial."""

        server, root = _make_server(tmp_path, require_write_approval=True)
        before = _read(root)
        result = server._call_tool(tool, params)
        assert result["data"].get("approval_required") is True
        assert result["data"].get("applied") is False
        # nothing on disk changed
        assert _read(root) == before
        server.close()


class TestGatePermitsApproved:
    def test_approved_write_applies(self, tmp_path: Path) -> None:
        """C2-2b: on + approved -> the edit is written as today."""

        server, root = _make_server(tmp_path, require_write_approval=True)
        result = server._call_tool(
            "opencontext_replace_symbol_body",
            {
                "symbol": "audit_login",
                "file": "src/auth.py",
                "body": "def audit_login(username: str) -> str:\n    return username.upper()",
                "approved": True,
            },
        )
        assert result["data"]["applied"] is True
        assert "approval_required" not in result["data"]
        assert "return username.upper()" in _read(root)
        server.close()


class TestReadAndMemoryToolsUnaffected:
    def test_read_tool_not_gated(self, tmp_path: Path) -> None:
        """C2-2c: a read tool is never subject to the write-approval gate."""

        server, _root = _make_server(tmp_path, require_write_approval=True)
        result = server._call_tool("opencontext_search", {"query": "audit_login"})
        assert "approval_required" not in result.get("data", result)
        server.close()

    def test_memory_tool_not_gated(self, tmp_path: Path) -> None:
        """C2-2c: a memory tool targets the store, not disk -> not gated.

        The fake runtime has no ``_v2_memory_store``, so the tool degrades to
        the structured "memory store unavailable" result — crucially WITHOUT an
        ``approval_required`` denial (the write-approval gate must not be in this
        path).
        """

        server, _root = _make_server(tmp_path, require_write_approval=True)
        result = server._call_tool("opencontext_memory_save", {"content": "a note"})
        assert "approval_required" not in result.get("data", result)
        assert result["data"].get("available") is False
        server.close()
