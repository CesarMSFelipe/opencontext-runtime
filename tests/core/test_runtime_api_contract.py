"""PR-013 SPEC-CLI-013-17: CLI run and MCP opencontext_run share the Runtime API
and return the same run-contract shape."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from opencontext_core.runtime.run_contract import RunContract, build_run_contract


class _Legacy:
    status = "passed"
    artifacts: ClassVar[list] = []
    gates: ClassVar[list] = []
    warnings: ClassVar[list] = []
    summary = "did the thing"


def test_build_run_contract_shape() -> None:
    contract = build_run_contract(
        session_id="sess-1",
        run_id="sdd-1",
        workflow="sdd",
        status="completed",
        legacy=_Legacy(),
    )
    assert isinstance(contract, RunContract)
    dumped = contract.model_dump()
    assert dumped["session_id"] == "sess-1"
    assert dumped["workflow"] == "sdd"
    assert dumped["summary"] == "did the thing"
    assert dumped["next_recommended"]
    for key in ("artifacts", "receipts", "gates", "cost", "confidence"):
        assert isinstance(dumped[key], dict)


def test_mcp_and_cli_share_runtime_api(tmp_path: Path, monkeypatch) -> None:
    """Both surfaces dispatch through RuntimeApi.run; the MCP path returns the
    build_run_contract shape over the same RuntimeApi result."""
    from opencontext_core.harness import runner as runner_mod
    from opencontext_core.mcp_stdio import MCPServer
    from opencontext_core.runtime.api import RunRequest, RuntimeApi, StartSessionRequest
    from opencontext_core.tools.policy import ToolPermissionPolicy

    class _Result:
        run_id = "legacy"
        status = "passed"
        artifacts: ClassVar[list] = []
        gates: ClassVar[list] = []
        warnings: ClassVar[list] = []

    monkeypatch.setattr(runner_mod.HarnessRunner, "run", lambda self, w, t, *a, **k: _Result())

    # Direct RuntimeApi path (what the CLI/run-contract builder consumes).
    api = RuntimeApi(root=tmp_path)
    ref = api.start_session(StartSessionRequest(task="t", root=str(tmp_path)))
    result = api.run(RunRequest(session_id=ref.session_id, workflow_id="sdd", task="t"))
    cli_contract = build_run_contract(
        session_id=ref.session_id,
        run_id=result.run_id,
        workflow="sdd",
        status=result.status,
        legacy=result.legacy,
    ).model_dump()

    # MCP path.
    server = MCPServer(db_path=tmp_path / "kg.db")
    server.policy = ToolPermissionPolicy(allowed_tools=set(server.tools.keys()))
    mcp_contract = server._handle_run({"task": "t", "workflow": "sdd", "root": str(tmp_path)})

    assert set(cli_contract) == set(mcp_contract)
    assert cli_contract["workflow"] == mcp_contract["workflow"] == "sdd"
