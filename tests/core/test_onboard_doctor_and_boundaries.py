from __future__ import annotations

from pathlib import Path

from opencontext_core.adapters.boundary import AdapterRequest, AdapterTarget
from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.doctor.checks import run_security_doctor
from opencontext_core.plugins.manifest import PluginManifest
from opencontext_core.workflow.engine import WorkflowEngine
from opencontext_core.workflow.hooks import ContextEngineHooks
from opencontext_core.workflow.steps import WorkflowServices
from opencontext_core.workspace.layout import ensure_workspace


def test_workspace_onboard_layout(tmp_path: Path) -> None:
    created = ensure_workspace(tmp_path)
    created_names = sorted(path.name for path in created)
    assert created_names == [
        "agents",
        "cache",
        "context-packs",
        "evals",
        "memory",
        "models",
        "plugins",
        "policies",
        "reports",
        "rules",
        "state",
        "templates",
        "traces",
        "workflows",
    ]
    for path in created:
        assert path.exists()
        assert path.is_dir()
    assert (tmp_path / ".opencontext/policies/tool-policy.yaml").read_text(encoding="utf-8")


def test_security_doctor_defaults_fail_closed() -> None:
    config = OpenContextConfig.model_validate(default_config_data())
    results = {check.name: check.ok for check in run_security_doctor(config)}
    assert results["tools.native.disabled"] is True
    assert results["tools.mcp.disabled"] is True
    assert results["providers.external_disabled"] is True


def test_traces_raw_check_reflects_actual_config_not_security_mode() -> None:
    # The check must verify the real trace-storage setting, not proxy through
    # security.mode (which false-failed a hardened developer-mode config).
    config = OpenContextConfig.model_validate(default_config_data())

    config.traces.store_raw_context = False
    raw_off = {c.name: c.ok for c in run_security_doctor(config)}
    assert raw_off["traces.raw.disabled"] is True

    config.traces.store_raw_context = True
    raw_on = {c.name: c.ok for c in run_security_doctor(config)}
    assert raw_on["traces.raw.disabled"] is False


def test_plugin_manifest_is_deny_by_default() -> None:
    manifest = PluginManifest(name="demo", version="1.0.0", entrypoint="plugins.demo:activate")
    assert manifest.permissions.read_paths == []
    assert manifest.permissions.write_paths == []
    assert manifest.permissions.network_hosts == []
    assert manifest.permissions.mcp_servers == []


def test_adapter_boundary_allows_supported_targets() -> None:
    request = AdapterRequest(target=AdapterTarget.CODEX, task="pack auth context")
    assert request.target is AdapterTarget.CODEX


def test_workflow_engine_calls_lifecycle_hooks() -> None:
    data = default_config_data()
    data["workflows"] = {"hook_test": {"steps": []}}
    config = OpenContextConfig.model_validate(data)
    calls: list[str] = []

    def before_run(_: object) -> None:
        calls.append("before")

    def after_run(_: object) -> None:
        calls.append("after")

    engine = WorkflowEngine(
        config,
        WorkflowServices(
            config=config,
            memory_store=object(),
            trace_logger=object(),
            llm_gateway=object(),
        ),
        registry={},
        hooks=ContextEngineHooks(before_run=before_run, after_run=after_run),
    )

    state = engine.run("hook_test", "question")
    assert state.workflow_name == "hook_test"
    assert calls == ["before", "after"]
