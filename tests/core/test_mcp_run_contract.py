"""PR-013 SPEC-CLI-013-15: opencontext_run returns the full contract, not counts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
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


def test_oc_flow_run_without_executor_cannot_complete(server: MCPServer, tmp_path: Path) -> None:
    out = server._handle_run(
        {"task": "Fix failing test", "workflow": "oc-flow", "root": str(tmp_path)}
    )
    assert _CONTRACT_KEYS <= set(out)
    assert out["workflow"] == "oc-flow"
    # No provider + a client that cannot sample: never a false "completed" and no
    # longer a bare needs_executor dead-end — the MCP layer hands the work to the
    # client agent while the underlying flow verdict stays visible.
    assert out["status"] == "agent_execute"
    assert out["status"] != "completed"
    assert out["oc_flow"]["status"] == "needs_executor"
    assert out["oc_flow"]["mutation_required"] is True
    assert out["follow_up"]["tool"] == "opencontext_session_apply"


def test_mcp_run_dispatcher_imports_without_server_side_effects() -> None:
    from opencontext_core.mcp.run_dispatcher import dispatch_mcp_run

    assert dispatch_mcp_run is not None


def test_auto_run_uses_oc_flow_selector_result(server: MCPServer, tmp_path: Path) -> None:
    out = server._handle_run(
        {"task": "Fix lint error in one file", "workflow": "auto", "root": str(tmp_path)}
    )
    assert out["selected_workflow"] == "oc-flow"
    # The selector still lands on OC Flow; with no executor available the MCP
    # layer upgrades the needs_executor verdict to the agent-execute handoff.
    assert out["status"] == "agent_execute"
    assert out["oc_flow"]["status"] == "needs_executor"


def test_sdd_run_includes_phase_metadata(server: MCPServer, tmp_path: Path, monkeypatch) -> None:
    from opencontext_core.models.trace import RunEvent

    class _Result:
        run_id = "sdd-id"
        status = "passed"
        artifacts: ClassVar[list] = []
        gates: ClassVar[list] = []
        warnings: ClassVar[list] = []
        events: ClassVar[list] = [
            RunEvent(index=0, phase="explore", action="run_phase", status="passed"),
            RunEvent(index=1, phase="verify", action="run_phase", status="warning"),
        ]

    captured: dict[str, str] = {}

    def _fake_run(self, workflow, task, *a, **k):
        captured["workflow"] = workflow
        return _Result()

    from opencontext_core.harness import runner as runner_mod

    monkeypatch.setattr(runner_mod.HarnessRunner, "run", _fake_run)

    out = server._handle_run(
        {"task": "do formal work", "workflow": "standard", "root": str(tmp_path)}
    )

    assert captured["workflow"] == "standard"
    assert out["selected_workflow"] == "standard"
    assert out["phases"] == ["explore", "verify"]
    assert out["phase_status"]["verify"] == "warning"
    assert out["verification_outcome"] == "warning"


def test_mcp_sdd_junk_phase_output_surfaces_warning(
    server: MCPServer, tmp_path: Path, monkeypatch
) -> None:
    """Junk spec output raises a phase_contract WARNING visible in gates.

    Hard blocking only occurs in sdd_strict mode; standard workflow surfaces
    the warning without stopping the run.
    """

    class _JunkDelegate:
        def delegate(self, phase: str, context: dict[str, object]) -> object:
            return SimpleNamespace(status="success", output="ok")

    from opencontext_core.harness import runner as runner_mod

    monkeypatch.setattr(runner_mod.HarnessRunner, "_build_executor", lambda self: _JunkDelegate())

    out = server._handle_run(
        {"task": "do formal work", "workflow": "standard", "root": str(tmp_path)}
    )

    gates = out.get("gates", {})
    assert any(
        gate_id == "phase_contract" and gate["status"] == "warning"
        for gate_id, gate in gates.items()
    ), "phase_contract WARNING must appear in gates for junk spec output"
