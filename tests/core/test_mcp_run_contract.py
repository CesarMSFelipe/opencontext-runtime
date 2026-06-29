"""PR-013 SPEC-CLI-013-15: opencontext_run returns the full contract, not counts."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from opencontext_core.mcp_stdio import MCPServer
from opencontext_core.tools.policy import ToolPermissionPolicy

_CONTRACT_KEYS = {
    "schema_version",
    "session_id",
    "run_id",
    "workflow",
    "status",
    "summary",
    "artifacts",
    "receipts",
    "gates",
    "cost",
    "confidence",
    "next_recommended",
}


@pytest.fixture
def server(tmp_path: Path) -> MCPServer:
    s = MCPServer(db_path=tmp_path / "kg.db")
    s.policy = ToolPermissionPolicy(allowed_tools=set(s.tools.keys()))
    return s


def test_run_contract_has_all_keys(server: MCPServer, tmp_path: Path, monkeypatch) -> None:
    class _Result:
        run_id = "legacy-id"
        status = "passed"
        artifacts: ClassVar[list] = []
        gates: ClassVar[list] = []
        warnings: ClassVar[list] = []

    def _fake_run(self, workflow, task, *a, **k):
        return _Result()

    from opencontext_core.harness import runner as runner_mod

    monkeypatch.setattr(runner_mod.HarnessRunner, "run", _fake_run)

    out = server._handle_run({"task": "do something", "root": str(tmp_path)})
    assert _CONTRACT_KEYS <= set(out)
    assert isinstance(out["artifacts"], dict)
    assert isinstance(out["gates"], dict)
    assert isinstance(out["receipts"], dict)
    assert isinstance(out["cost"], dict)
    assert isinstance(out["confidence"], dict)
    assert out["session_id"].startswith("sess-")
    assert out["next_recommended"]


def test_run_requires_task(server: MCPServer) -> None:
    out = server._handle_run({})
    assert "error" in out
    assert out["code"] == "output_contract_failed"
    assert out["next_action"]
