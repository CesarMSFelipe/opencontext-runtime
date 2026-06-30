"""MCP sampling executor drives OC Flow through ApplyEdit pipeline."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from opencontext_core.llm.sampling_gateway import register_host_sampler
from opencontext_core.mcp_stdio import MCPServer
from opencontext_core.oc_flow import cli as oc_flow_cli
from opencontext_core.oc_flow.cli import _resolve_executor, run_oc_flow_cli
from opencontext_core.oc_flow.mcp_executor import MCPSamplingNodeExecutor
from opencontext_core.oc_flow.nodes import _parse_apply_edit_set
from opencontext_core.providers.detect import DetectedProvider

_GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "oc_flow_bugfix_python"
_VALID_EDIT_JSON = (
    '[{"path":"buggy_add.py","operation":"replace_range","start_line":2,"end_line":2,'
    '"content":"    return a + b","reason":"fix the operator",'
    '"requirement_refs":["add returns the sum"]}]'
)


@pytest.fixture(autouse=True)
def _clear_sampler():
    register_host_sampler(None)
    yield
    register_host_sampler(None)


def _pin_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        oc_flow_cli,
        "detect_provider",
        lambda: DetectedProvider(name="mock", api_key="", model="mock", source="fallback"),
    )


def test_resolve_executor_prefers_mcp_sampling_when_available(tmp_path: Path, monkeypatch) -> None:
    _pin_mock(monkeypatch)
    register_host_sampler(lambda *_: _VALID_EDIT_JSON)

    executor = _resolve_executor(tmp_path)

    assert isinstance(executor, MCPSamplingNodeExecutor)


def test_sampling_applyedit_contract_accepts_delete_file_and_rejects_bad_range() -> None:
    assert _parse_apply_edit_set(
        '[{"path":"old.py","operation":"delete_file","reason":"remove",'
        '"requirement_refs":["gone"]}]'
    )
    assert _parse_apply_edit_set(
        '[{"path":"calc.py","operation":"replace_range","start_line":4,"end_line":2,'
        '"content":"x","reason":"bad","requirement_refs":["c"]}]'
    ) is None


def test_mcp_sampling_cli_fix_runs_full_pipeline(tmp_path: Path, monkeypatch) -> None:
    _pin_mock(monkeypatch)
    work = tmp_path / "fixture"
    shutil.copytree(_GOLDEN, work)
    register_host_sampler(lambda *_: _VALID_EDIT_JSON)

    summary = run_oc_flow_cli("Fix failing test", root=work, workflow="auto", lane="fast")

    assert summary["status"] == "completed"
    assert (work / "buggy_add.py").read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"
    assert (Path(summary["artifacts_dir"]) / "apply-receipts.json").exists()


def test_mcp_opencontext_run_uses_sampling_executor(tmp_path: Path, monkeypatch) -> None:
    _pin_mock(monkeypatch)
    work = tmp_path / "fixture"
    shutil.copytree(_GOLDEN, work)
    register_host_sampler(lambda *_: _VALID_EDIT_JSON)
    server = MCPServer(db_path=tmp_path / "kg.db")

    out = server._handle_run({"task": "Fix failing test", "workflow": "oc-flow", "root": str(work)})

    assert out["status"] == "completed"
    assert out["host_model_used"] is True
    assert (work / "buggy_add.py").read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"
    server.close()


def test_mcp_sampling_malformed_response_blocks_without_mutation(tmp_path: Path, monkeypatch) -> None:
    _pin_mock(monkeypatch)
    work = tmp_path / "fixture"
    shutil.copytree(_GOLDEN, work)
    register_host_sampler(lambda *_: "ok")

    summary = run_oc_flow_cli("Fix failing test", root=work, workflow="auto", lane="fast")

    assert summary["status"] == "blocked"
    assert "sampling response failed ApplyEdit contract validation" in summary["completion_reason"]
    assert (work / "buggy_add.py").read_text(encoding="utf-8") == "def add(a, b):\n    return a - b\n"


def test_mcp_sampling_secret_file_edit_blocks_before_apply(tmp_path: Path, monkeypatch) -> None:
    _pin_mock(monkeypatch)
    work = tmp_path / "fixture"
    shutil.copytree(_GOLDEN, work)
    register_host_sampler(
        lambda *_: '[{"path":".env","operation":"create_file","content":"OPENAI_API_KEY=sk-test",'
        '"reason":"bad","requirement_refs":["c"]}]'
    )

    summary = run_oc_flow_cli("Fix failing test", root=work, workflow="auto", lane="fast")

    assert summary["status"] == "blocked"
    assert not (work / ".env").exists()
