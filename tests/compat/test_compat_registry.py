"""Adapter protocol + registry + harness-adapter parity (SPEC CL-001/002/003/004)."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.compat import (
    AdapterRegistry,
    HarnessApiAdapter,
    LegacyAdapter,
    LegacyWorkflowAdapter,
)
from opencontext_core.runtime.api import RunRequest, RuntimeApi, StartSessionRequest


class _FakeResult:
    def __init__(self, run_id: str = "sdd-legacy", status: str = "passed") -> None:
        self.run_id = run_id
        self.status = status


class _FakeHarness:
    def __init__(self, result: _FakeResult) -> None:
        self._result = result
        self.calls: list[tuple[str, str]] = []

    def run(self, workflow: str, task: str) -> _FakeResult:
        self.calls.append((workflow, task))
        return self._result

    def schedule_phases(self, workflow: str) -> list[str]:
        return ["explore", "apply"]


def test_harness_adapter_conforms_to_protocol() -> None:
    adapter = HarnessApiAdapter()
    assert isinstance(adapter, LegacyAdapter)
    assert adapter.subsystem == "runtime"
    assert adapter.flag == "runtime.session_wrapper"


def test_register_resolve_and_duplicate_guard() -> None:
    reg = AdapterRegistry()
    adapter = HarnessApiAdapter()
    reg.register(adapter)

    assert reg.get("runtime") is adapter
    assert reg.subsystems() == ["runtime"]
    assert reg.resolve("runtime", flag_enabled=False) == adapter.legacy
    assert reg.resolve("runtime", flag_enabled=True) == adapter.adapt
    assert reg.resolve("unknown", flag_enabled=True) is None

    with pytest.raises(ValueError):
        reg.register(HarnessApiAdapter())


def test_harness_adapter_preserves_legacy_result_on_both_routes(tmp_path: Path) -> None:
    sentinel = _FakeResult(run_id="sdd-xyz", status="passed")
    fake = _FakeHarness(sentinel)
    adapter = HarnessApiAdapter(tmp_path, harness_factory=lambda root: fake)

    # Legacy route: HarnessRunner.run() called directly, no session writes.
    res_legacy = adapter.legacy(RunRequest(session_id="ignored", workflow_id="sdd", task="do x"))
    assert res_legacy.legacy is sentinel
    assert not (tmp_path / ".opencontext" / "sessions").exists()

    # vNext route: session-bracketed run (needs a session first).
    api = RuntimeApi(tmp_path, harness_factory=lambda root: fake)
    ref = api.start_session(StartSessionRequest(task="do x", root=str(tmp_path)))
    res_adapt = adapter.adapt(RunRequest(session_id=ref.session_id, workflow_id="sdd"))

    # Parity: both routes return the byte-equal legacy result (same object).
    assert res_adapt.legacy is sentinel
    assert res_legacy.legacy is res_adapt.legacy


def test_registry_routes_to_distinct_subsystems() -> None:
    reg = AdapterRegistry()
    reg.register(HarnessApiAdapter())
    reg.register(LegacyWorkflowAdapter())

    runtime_route = reg.resolve("runtime", flag_enabled=False)
    workflow_route = reg.resolve("workflow_registry", flag_enabled=False)

    assert runtime_route is not None
    assert workflow_route is not None
    assert runtime_route != workflow_route
