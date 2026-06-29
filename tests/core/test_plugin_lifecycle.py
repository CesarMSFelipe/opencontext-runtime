"""PR-015 compatibility + lifecycle tests (AC-CP1/RG2/OB1, PLG-CONV)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from opencontext_core.config import PluginHostConfig
from opencontext_core.personas.registry import PersonaRegistry
from opencontext_core.plugin_system import PluginRegistry
from opencontext_core.plugins.compatibility import check_compatibility
from opencontext_core.plugins.extension_points import ExtensionPoint
from opencontext_core.plugins.lifecycle import (
    LifecycleStage,
    LifecycleStatus,
    activate_plugin,
)
from opencontext_core.plugins.manifest import PluginManifest

_HEALTHY = "class OpenContextPlugin:\n    def health(self):\n        return True\n"
_SICK = "class OpenContextPlugin:\n    def health(self):\n        return False\n"


def _registry(tmp_path: Path) -> PluginRegistry:
    return PluginRegistry(tmp_path)


def _make(tmp_path: Path, name: str, manifest: dict, *, body: str = _HEALTHY) -> None:
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    (d / "plugin.py").write_text(body, encoding="utf-8", newline="")
    manifest.setdefault("name", name)
    manifest.setdefault("version", "1.0.0")
    manifest.setdefault("entry_point", "plugin.py")
    manifest.setdefault("enabled", True)
    manifest.setdefault("schema_version", "opencontext.plugin.v1")
    manifest["entry_checksum"] = "sha256:" + hashlib.sha256(body.encode()).hexdigest()
    (d / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")


# ── Compatibility (AC-CP1) ───────────────────────────────────────────────────
def test_incompatible_plugin_disabled_not_activated(tmp_path: Path) -> None:
    _make(
        tmp_path,
        "toonew",
        {"id": "x.toonew", "requires": {"runtime": ">=99.0"}, "contributes": {"personas": ["p"]}},
    )
    res = activate_plugin(_registry(tmp_path), "toonew", core_version="1.5.0")
    assert res.status is LifecycleStatus.INCOMPATIBLE
    assert res.stage is LifecycleStage.COMPATIBILITY
    assert "99.0" in res.reason
    assert res.plugin_obj is None


def test_compatible_plugin_proceeds() -> None:
    m = PluginManifest.model_validate(
        {
            "name": "ok",
            "version": "1.0.0",
            "entrypoint": "plugin.py",
            "requires": {"runtime": ">=1.0"},
        }
    )
    assert check_compatibility(m, "1.5.0").ok


def test_discover_annotates_incompatibility(tmp_path: Path) -> None:
    _make(tmp_path, "toonew", {"id": "x.toonew", "requires": {"runtime": ">=99.0"}})
    info = _registry(tmp_path).get_info("toonew")
    assert info is not None
    assert info.incompatible  # discovered but flagged


# ── Lifecycle pipeline (AC-RG2) ──────────────────────────────────────────────
def test_dependency_resolution_precedes_activation(tmp_path: Path) -> None:
    _make(
        tmp_path,
        "needs",
        {
            "id": "x.needs",
            "requires": {"runtime": ">=1.0", "plugins": ["absent-dep"]},
            "contributes": {"personas": ["p"]},
        },
    )
    res = activate_plugin(_registry(tmp_path), "needs", core_version="1.5.0")
    assert res.status is LifecycleStatus.FAILED
    assert res.stage is LifecycleStage.RESOLVE_DEPENDENCIES
    assert res.plugin_obj is None


def test_missing_capability_halts_at_resolve(tmp_path: Path) -> None:
    _make(
        tmp_path,
        "capreq",
        {
            "id": "x.capreq",
            "requires": {"runtime": ">=1.0", "capabilities": ["gpu"]},
            "contributes": {"personas": ["p"]},
        },
    )
    res = activate_plugin(
        _registry(tmp_path), "capreq", core_version="1.5.0", available_capabilities=set()
    )
    assert res.status is LifecycleStatus.FAILED
    assert res.stage is LifecycleStage.RESOLVE_DEPENDENCIES


def test_health_check_gates_active_status(tmp_path: Path) -> None:
    _make(tmp_path, "sick", {"id": "x.sick", "contributes": {"personas": ["p"]}}, body=_SICK)
    res = activate_plugin(_registry(tmp_path), "sick", core_version="1.5.0")
    assert res.status is LifecycleStatus.UNHEALTHY
    assert res.stage is LifecycleStage.HEALTH_CHECK


def test_contribution_routes_into_target_registry(tmp_path: Path) -> None:
    _make(
        tmp_path,
        "demo",
        {"id": "opencontext.demo", "contributes": {"personas": ["oc-demo-engineer"]}},
    )
    pr = PersonaRegistry()
    res = activate_plugin(
        _registry(tmp_path), "demo", core_version="1.5.0", sinks={ExtensionPoint.PERSONAS: pr}
    )
    assert res.status is LifecycleStatus.ACTIVE
    assert pr.has("oc-demo-engineer")
    persona = pr.get("oc-demo-engineer")
    # PLG-CONV: contributions register under PLUGIN provenance, untrusted by default.
    assert persona.metadata.source.value == "plugin"
    assert persona.metadata.trust.value == "untrusted"
    assert persona.metadata.plugin_id == "opencontext.demo"


def test_no_contributes_falls_back_to_legacy_load(tmp_path: Path) -> None:
    _make(tmp_path, "legacy", {"id": "x.legacy"})  # no contributes
    res = activate_plugin(_registry(tmp_path), "legacy", core_version="1.5.0")
    assert res.status is LifecycleStatus.ACTIVE
    assert res.plugin_obj is not None  # loaded via legacy path


def test_contracts_disabled_routes_legacy(tmp_path: Path) -> None:
    _make(tmp_path, "demo", {"id": "x.demo", "contributes": {"personas": ["p"]}})
    res = activate_plugin(
        _registry(tmp_path),
        "demo",
        core_version="1.5.0",
        host_config=PluginHostConfig(contracts_enabled=False),
    )
    assert res.status is LifecycleStatus.ACTIVE
    assert res.reason == "legacy_path"


# ── Observability (AC-OB1) ───────────────────────────────────────────────────
def test_activation_emits_receipt_and_contribution_event(tmp_path: Path) -> None:
    _make(
        tmp_path,
        "demo",
        {"id": "opencontext.demo", "contributes": {"personas": ["oc-demo-engineer"]}},
    )
    pr = PersonaRegistry()
    res = activate_plugin(
        _registry(tmp_path), "demo", core_version="1.5.0", sinks={ExtensionPoint.PERSONAS: pr}
    )
    # Receipt references the plugin and its contributions.
    assert res.receipt is not None
    assert res.receipt.plugin_id == "demo"
    assert res.receipt.contributions[0].contribution_id == "oc-demo-engineer"
    assert "activate" in res.receipt.stages and "discover" in res.receipt.stages
    # A contribution is attributable by extension point + id.
    contrib_events = [e for e in res.events if e.type == "contribution"]
    assert contrib_events
    assert contrib_events[0].extension_point == "personas"
    assert contrib_events[0].contribution_id == "oc-demo-engineer"
