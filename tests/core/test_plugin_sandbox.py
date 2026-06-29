"""PR-015 enforcement tests: sandbox, benchmark gate, isolation (AC-SB1/SB2/BM1/IS1)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from opencontext_core.actions.policy import ActionRequest, ActionType, evaluate_action
from opencontext_core.plugin_system import PluginRegistry
from opencontext_core.plugins.benchmark_gate import benchmark_gate
from opencontext_core.plugins.lifecycle import (
    LifecycleStage,
    LifecycleStatus,
    activate_plugin,
)
from opencontext_core.plugins.manifest import PluginManifest, PluginPermissions
from opencontext_core.plugins.sandbox import (
    CapabilityBroker,
    run_sandboxed,
    verify_entry_checksum,
)

_HEALTHY = "class OpenContextPlugin:\n    def health(self):\n        return True\n"


def _broker(tmp_path: Path, perms: PluginPermissions) -> CapabilityBroker:
    reg = PluginRegistry(tmp_path)
    reg.register_declared_permissions("p", perms)
    return CapabilityBroker(reg, "p")


# ── Capability broker (AC-SB2) ───────────────────────────────────────────────
def test_undeclared_command_denied_at_broker(tmp_path: Path) -> None:
    broker = _broker(tmp_path, PluginPermissions())  # nothing granted
    decision = broker.check("command", "git")
    assert decision.allowed is False
    assert decision.reason == "capability_not_declared"


def test_undeclared_kg_write_denied_at_broker(tmp_path: Path) -> None:
    broker = _broker(tmp_path, PluginPermissions())
    assert broker.allowed("kg_write", "project") is False


def test_unknown_capability_denied(tmp_path: Path) -> None:
    broker = _broker(tmp_path, PluginPermissions(command=["*"]))
    assert broker.allowed("teleport", "anywhere") is False


# ── Cannot self-grant / routes through policy (AC-IS1) ────────────────────────
def test_declared_command_still_routes_through_policy(tmp_path: Path) -> None:
    """A granted capability cannot self-approve: policy still gates it."""
    broker = _broker(tmp_path, PluginPermissions(command=["git"]))
    # Declared, but CALL_TOOL requires human approval -> not allowed yet.
    assert broker.allowed("command", "git") is False
    assert broker.check("command", "git").requires_approval is True
    # With approval, the policy lets it proceed.
    assert broker.allowed("command", "git", approved=True) is True


def test_write_outside_sandbox_boundary_denied() -> None:
    """AC-SB1 scenario 2: a write with sandbox disabled is denied by policy."""
    decision = evaluate_action(ActionRequest(action=ActionType.WRITE_FILE, sandbox_enabled=False))
    assert decision.allowed is False
    assert decision.reason == "write_requires_explicit_sandbox"


# ── Degrade-loud (AC-SB2 scenario 2) ─────────────────────────────────────────
def _make_plugin(tmp_path: Path, name: str, body: str = _HEALTHY) -> tuple[Path, str]:
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    (d / "plugin.py").write_text(body, encoding="utf-8", newline="")
    checksum = "sha256:" + hashlib.sha256(body.encode()).hexdigest()
    return d, checksum


def test_unavailable_isolation_degrades_loudly(tmp_path: Path) -> None:
    d, checksum = _make_plugin(tmp_path, "demo")
    result = run_sandboxed(
        d, plugin_name="demo", entry_checksum=checksum, isolation_probe=lambda: False
    )
    assert result.ok is True
    assert result.degraded is True  # never silently unrestricted
    assert "sandbox_unavailable" in result.warnings


def test_available_isolation_not_degraded(tmp_path: Path) -> None:
    d, checksum = _make_plugin(tmp_path, "demo")
    result = run_sandboxed(
        d, plugin_name="demo", entry_checksum=checksum, isolation_probe=lambda: True
    )
    assert result.ok is True
    assert result.degraded is False


# ── Integrity / tamper (AC-SB1) ──────────────────────────────────────────────
def test_tampered_entry_refused_by_sandbox(tmp_path: Path) -> None:
    d, _ = _make_plugin(tmp_path, "evil")
    result = run_sandboxed(
        d, plugin_name="evil", entry_checksum="sha256:" + "0" * 64, isolation_probe=lambda: False
    )
    assert result.ok is False
    assert result.reason == "entry_checksum_mismatch"


def test_verify_entry_checksum_helper(tmp_path: Path) -> None:
    body = "x = 1\n"
    f = tmp_path / "m.py"
    f.write_text(body, encoding="utf-8", newline="")
    good = "sha256:" + hashlib.sha256(body.encode()).hexdigest()
    assert verify_entry_checksum(f, good) is True
    assert verify_entry_checksum(f, "sha256:" + "0" * 64) is False
    assert verify_entry_checksum(f, "") is True  # unverified-but-permitted


def test_tampered_entry_refused_via_lifecycle(tmp_path: Path) -> None:
    d, _ = _make_plugin(tmp_path, "evil")
    manifest = {
        "name": "evil",
        "version": "1.0.0",
        "entry_point": "plugin.py",
        "enabled": True,
        "schema_version": "opencontext.plugin.v1",
        "id": "x.evil",
        "contributes": {"personas": ["p"]},
        "entry_checksum": "sha256:" + "0" * 64,  # wrong
    }
    (d / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    res = activate_plugin(PluginRegistry(tmp_path), "evil", core_version="1.5.0")
    assert res.status is LifecycleStatus.FAILED
    assert res.stage is LifecycleStage.ACTIVATE
    assert res.reason == "entry_checksum_mismatch"


# ── Failure isolation (AC-IS1) ───────────────────────────────────────────────
def test_crashing_plugin_is_isolated(tmp_path: Path) -> None:
    body = "raise RuntimeError('boom at import')\n"
    d, checksum = _make_plugin(tmp_path, "boom", body=body)
    manifest = {
        "name": "boom",
        "version": "1.0.0",
        "entry_point": "plugin.py",
        "enabled": True,
        "schema_version": "opencontext.plugin.v1",
        "id": "x.boom",
        "contributes": {"personas": ["p"]},
        "entry_checksum": checksum,
    }
    (d / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    # Must not raise out of the lifecycle.
    res = activate_plugin(PluginRegistry(tmp_path), "boom", core_version="1.5.0")
    assert res.status is LifecycleStatus.FAILED
    assert res.stage is LifecycleStage.ACTIVATE
    assert "activation_failed" in res.reason


# ── Benchmark gate (AC-BM1) ──────────────────────────────────────────────────
def _manifest_with_suite(suites: list[str]) -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "name": "b",
            "version": "1.0.0",
            "entrypoint": "plugin.py",
            "contributes": {"benchmark_suites": suites},
        }
    )


def test_failing_benchmark_blocks() -> None:
    gate = benchmark_gate(_manifest_with_suite(["s1"]), enabled=True, runner=lambda m: False)
    assert gate.passed is False
    assert gate.ran is True
    assert gate.reason == "benchmark_failed"


def test_passing_benchmark_allows() -> None:
    gate = benchmark_gate(_manifest_with_suite(["s1"]), enabled=True, runner=lambda m: True)
    assert gate.passed is True and gate.ran is True


def test_no_suite_passes_through() -> None:
    gate = benchmark_gate(_manifest_with_suite([]), enabled=True, runner=lambda m: False)
    assert gate.passed is True and gate.ran is False
    assert gate.reason == "no_benchmark_suite"


def test_absent_framework_passes_through() -> None:
    gate = benchmark_gate(_manifest_with_suite(["s1"]), enabled=True, runner=None)
    assert gate.passed is True and gate.ran is False
    assert gate.reason == "benchmark_framework_absent"


def test_failing_benchmark_blocks_activation(tmp_path: Path) -> None:
    body = _HEALTHY
    d, checksum = _make_plugin(tmp_path, "bench", body=body)
    manifest = {
        "name": "bench",
        "version": "1.0.0",
        "entry_point": "plugin.py",
        "enabled": True,
        "schema_version": "opencontext.plugin.v1",
        "id": "x.bench",
        "contributes": {"benchmark_suites": ["s1"], "personas": ["p"]},
        "entry_checksum": checksum,
    }
    (d / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    res = activate_plugin(
        PluginRegistry(tmp_path), "bench", core_version="1.5.0", benchmark_runner=lambda m: False
    )
    assert res.status is LifecycleStatus.FAILED
    assert res.stage is LifecycleStage.BENCHMARK_GATE
