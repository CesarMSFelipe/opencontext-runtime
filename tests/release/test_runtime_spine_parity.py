"""C14 — Runtime spine parity suite (OQ-2 + three shape checks).

Verifies parity BEFORE the spine flip (C15) so the gating condition for the
flip is unambiguously established in source history:

1. OQ-2: rt_spine / mcp_runtime are registered in FLIP_SEQUENCE + SUBSYSTEM_FLAGS.
2. CLI shape: ``run_oc_flow_cli`` produces the contract-required keys.
3. RuntimeApi shape: ``start_session`` + ``run`` produce parity shape.
4. MCP tools: ``runtime_dispatcher.registered_tools()`` returns the 9 session
   tools when the mcp-runtime flag is migrated.
5. TUI start path: ``data.set_state`` accepts a RuntimeApi session ref without error.

All tests exercise RuntimeApi or compat machinery directly — they do NOT require
the ``rt-spine`` flag to be migrated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from opencontext_core.compat.flip_evidence import FLIP_SEQUENCE, SUBSYSTEM_FLAGS

# ── OQ-2: FLIP_SEQUENCE / SUBSYSTEM_FLAGS ─────────────────────────────────────


def test_rt_spine_in_flip_sequence_and_subsystem_flags() -> None:
    """OQ-2: rt_spine is documented in FLIP_SEQUENCE and maps to runtime.rt-spine."""
    assert "rt_spine" in FLIP_SEQUENCE, "rt_spine missing from FLIP_SEQUENCE"
    assert "rt_spine" in SUBSYSTEM_FLAGS, "rt_spine missing from SUBSYSTEM_FLAGS"
    assert SUBSYSTEM_FLAGS["rt_spine"] == "runtime.rt-spine"


def test_mcp_runtime_in_flip_sequence_and_subsystem_flags() -> None:
    """OQ-2: mcp_runtime is documented in FLIP_SEQUENCE and maps to runtime.mcp-runtime."""
    assert "mcp_runtime" in FLIP_SEQUENCE, "mcp_runtime missing from FLIP_SEQUENCE"
    assert "mcp_runtime" in SUBSYSTEM_FLAGS, "mcp_runtime missing from SUBSYSTEM_FLAGS"
    assert SUBSYSTEM_FLAGS["mcp_runtime"] == "runtime.mcp-runtime"


def test_rt_spine_precedes_mcp_runtime_in_flip_sequence() -> None:
    """rt_spine must be flipped before mcp_runtime (spine before dispatcher)."""
    idx_spine = list(FLIP_SEQUENCE).index("rt_spine")
    idx_mcp = list(FLIP_SEQUENCE).index("mcp_runtime")
    assert idx_spine < idx_mcp, "rt_spine must precede mcp_runtime in FLIP_SEQUENCE"


# ── shape: run_oc_flow_cli has the required contract keys ─────────────────────


def test_run_oc_flow_cli_shape_has_contract_keys(tmp_path: Path) -> None:
    """run_oc_flow_cli returns the canonical run-contract keys: status, run_id, session_id."""
    from opencontext_core.oc_flow.cli import run_oc_flow_cli

    summary = run_oc_flow_cli(
        "Fix failing test in tests/unit/test_parser.py",
        root=tmp_path,
        workflow="auto",
        enabled=True,
    )
    assert "status" in summary, f"'status' missing from cli summary: {list(summary)}"
    assert "run_id" in summary, f"'run_id' missing from cli summary: {list(summary)}"
    assert "session_id" in summary, f"'session_id' missing from cli summary: {list(summary)}"
    assert "final_node" in summary, f"'final_node' missing from cli summary: {list(summary)}"
    assert "workflow" in summary, f"'workflow' missing from cli summary: {list(summary)}"


# ── shape: RuntimeApi session-first contract ───────────────────────────────────


class _StubHarness:
    """Minimal stub that returns an OCFlowRunResult without running anything."""

    def run(self, workflow: str, task: str, **_: Any) -> Any:
        from opencontext_core.oc_flow.runner import OCFlowRunResult

        return OCFlowRunResult(
            run_id="run-stub",
            session_id="sess-stub",
            status="needs_executor",
            final_node="completed",
        )


def test_runtime_api_start_session_produces_session_ref(tmp_path: Path) -> None:
    """RuntimeApi.start_session returns a SessionRef with session_id, status, session_path."""
    from opencontext_core.runtime.api import RuntimeApi, StartSessionRequest

    api = RuntimeApi(tmp_path, harness_factory=lambda root: _StubHarness())
    ref = api.start_session(StartSessionRequest(task="fix test", root=str(tmp_path)))
    assert ref.session_id
    assert ref.status
    assert ref.session_path


def test_runtime_api_run_produces_run_result_with_parity_fields(tmp_path: Path) -> None:
    """RuntimeApi.run returns RunResult carrying run_id, status, and the legacy result."""
    from opencontext_core.runtime.api import RunRequest, RuntimeApi, StartSessionRequest

    api = RuntimeApi(tmp_path, harness_factory=lambda root: _StubHarness())
    ref = api.start_session(StartSessionRequest(task="fix test", root=str(tmp_path)))
    result = api.run(RunRequest(session_id=ref.session_id, workflow_id="oc-flow", task="fix test"))
    assert result.run_id
    assert result.status
    # The legacy carrier exposes final_node and status for downstream projection.
    legacy = result.legacy
    assert hasattr(legacy, "status"), "legacy result must have 'status'"
    assert hasattr(legacy, "final_node"), "legacy result must have 'final_node'"
    assert hasattr(legacy, "workflow_selection"), "legacy result must have 'workflow_selection'"


def test_runtime_api_run_threads_session_id(tmp_path: Path) -> None:
    """The RunResult run_id is distinct from the session_id (session-first contract)."""
    from opencontext_core.runtime.api import RunRequest, RuntimeApi, StartSessionRequest

    api = RuntimeApi(tmp_path, harness_factory=lambda root: _StubHarness())
    ref = api.start_session(StartSessionRequest(task="task", root=str(tmp_path)))
    result = api.run(RunRequest(session_id=ref.session_id, workflow_id="oc-flow", task="task"))
    # run_id and session_id are different identifiers in the session-first contract.
    assert result.run_id != ref.session_id


# ── MCP: runtime_dispatcher returns 9 tools when mcp-runtime is migrated ──────


def test_mcp_registered_tools_empty_when_flag_off() -> None:
    """When mcp-runtime is NOT migrated, registered_tools() returns no runtime.* tools."""
    from opencontext_core.mcp import runtime_dispatcher

    with patch.object(runtime_dispatcher, "_is_migrated_flag", return_value=False):
        tools = runtime_dispatcher.registered_tools()
    assert tools == []


def test_mcp_registered_tools_returns_nine_when_flag_migrated() -> None:
    """When mcp-runtime IS migrated, registered_tools() returns exactly 9 session tools."""
    from opencontext_core.mcp import runtime_dispatcher

    with patch.object(runtime_dispatcher, "_is_migrated_flag", return_value=True):
        tools = runtime_dispatcher.registered_tools()
    assert len(tools) == 9
    assert "runtime.start_session" in tools
    assert "runtime.run" in tools
    assert "runtime.next" in tools
    assert "runtime.observe" in tools
    assert "runtime.apply" in tools
    assert "runtime.inspect" in tools
    assert "runtime.resume" in tools
    assert "runtime.archive" in tools
    assert "runtime.status" in tools


def test_mcp_build_run_contract_has_canonical_keys() -> None:
    """build_run_contract (used by legacy MCP dispatcher) has session_id/run_id/workflow/status."""
    from opencontext_core.runtime.run_contract import RunContract

    fields = set(RunContract.model_fields)
    for required in ("session_id", "run_id", "workflow", "status"):
        assert required in fields, f"RunContract missing field: {required}"


# ── TUI: start path accepts RuntimeApi session data ───────────────────────────


# ── status vocabulary parity (C15 regression pin) ────────────────────────────


def test_legacy_status_preserves_oc_flow_terminal_vocabulary() -> None:
    """_legacy_status must pass OC Flow terminal statuses through unchanged (C15 fix).

    Before the C15 fix, _legacy_status mapped *every* unrecognised text
    (including "needs_executor", "needs_provider") to "completed".  The public
    ``opencontext run --json`` output must preserve the OC Flow vocabulary so
    callers that branch on "completed" vs "needs_executor" are not misled.
    """
    from opencontext_core.runtime.api import RuntimeApi

    _ls = RuntimeApi._legacy_status

    class _R:
        def __init__(self, s: str) -> None:
            self.status = s

    # OC Flow terminal values must survive unchanged.
    assert _ls(_R("completed")) == "completed"
    assert _ls(_R("needs_executor")) == "needs_executor"
    assert _ls(_R("needs_provider")) == "needs_provider"
    assert _ls(_R("blocked")) == "blocked"
    assert _ls(_R("escalated")) == "escalated"
    assert _ls(_R("needs_verification")) == "needs_verification"
    assert _ls(_R("needs_user_edit")) == "needs_user_edit"

    # Harness GateStatus values must translate to runtime vocabulary.
    from opencontext_core.harness.models import GateStatus

    class _H:
        def __init__(self, s: GateStatus) -> None:
            self.status = s

    assert _ls(_H(GateStatus.PASSED)) == "completed"
    assert _ls(_H(GateStatus.WARNING)) == "completed_with_warnings"
    assert _ls(_H(GateStatus.FAILED)) == "failed"
    assert _ls(_H(GateStatus.SKIPPED)) == "scaffolded"


def test_oc_flow_harness_adapter_routes_to_ocflow_runner(tmp_path: Path) -> None:
    """_OCFlowHarness.run returns OCFlowRunResult so status vocabulary is correct.

    This pins the C15-introduced routing: RuntimeApi for "oc-flow" / "auto"
    workflows must use _OCFlowHarness (which returns OCFlowRunResult with
    'completed'/'needs_executor' vocabulary), NOT HarnessRunner (which would
    return HarnessRunResult with GateStatus.PASSED='passed').
    """
    from opencontext_core.oc_flow.runner import OCFlowRunResult
    from opencontext_core.runtime.api import RunRequest, RuntimeApi, StartSessionRequest

    api = RuntimeApi(tmp_path)
    ref = api.start_session(StartSessionRequest(task="Fix bug", root=str(tmp_path)))
    result = api.run(RunRequest(session_id=ref.session_id, workflow_id="oc-flow", task="Fix bug"))

    # The legacy carrier must be an OCFlowRunResult (not HarnessRunResult).
    assert isinstance(result.legacy, OCFlowRunResult), (
        f"expected OCFlowRunResult, got {type(result.legacy).__name__}: "
        "RuntimeApi routes oc-flow via _OCFlowHarness → OCFlowRunResult"
    )
    # Public status must be in the OC Flow terminal vocabulary (not "passed").
    oc_flow_vocab = {
        "completed",
        "needs_executor",
        "needs_provider",
        "blocked",
        "escalated",
        "needs_verification",
        "needs_user_edit",
    }
    assert result.status in oc_flow_vocab, (
        f"status {result.status!r} is not in OC Flow vocabulary; "
        "the harness vocabulary leak ('passed') has been reintroduced"
    )


def test_oc_flow_disabled_yaml_returns_blocked_not_crash(tmp_path: Path) -> None:
    """runtime.oc_flow_enabled: false in YAML must return a blocked result, not raise.

    F2: _OCFlowHarness must read the project config and honor oc_flow_enabled=false
    by returning an OCFlowRunResult(status='blocked') instead of running the flow.
    """
    import yaml

    from opencontext_core.oc_flow.runner import OCFlowRunResult
    from opencontext_core.runtime.api import RunRequest, RuntimeApi, StartSessionRequest

    # Write a project config that disables OC Flow.
    (tmp_path / "opencontext.yaml").write_text(
        yaml.safe_dump({"runtime": {"oc_flow_enabled": False}}),
        encoding="utf-8",
    )

    api = RuntimeApi(tmp_path)
    ref = api.start_session(StartSessionRequest(task="Fix bug", root=str(tmp_path)))
    # Must NOT raise; must return a blocked result.
    result = api.run(RunRequest(session_id=ref.session_id, workflow_id="oc-flow", task="Fix bug"))

    assert isinstance(result.legacy, OCFlowRunResult), (
        f"expected OCFlowRunResult, got {type(result.legacy).__name__}"
    )
    assert result.legacy.status == "blocked", (
        f"expected status='blocked' when oc_flow_enabled=false, got {result.legacy.status!r}"
    )
    assert result.status == "blocked"


def test_tui_data_set_state_accepts_runtime_api_session(tmp_path: Path) -> None:
    """TUI data.set_state accepts fields from a RuntimeApi.start_session result."""
    from opencontext_studio.tui import data

    from opencontext_core.runtime.api import RuntimeApi, StartSessionRequest

    api = RuntimeApi(tmp_path, harness_factory=lambda root: _StubHarness())
    ref = api.start_session(StartSessionRequest(task="test task", root=str(tmp_path)))

    # Seed TUI state from the session ref (the future production wiring shape).
    data.set_state(session_id=ref.session_id, run_id="", project=str(tmp_path))
    state = data.get_state()

    assert state["session_id"] == ref.session_id
    assert state["project"] == str(tmp_path)
