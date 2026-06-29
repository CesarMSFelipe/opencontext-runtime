"""Full plugin lifecycle state machine (PR-015, doc 60 item 13, book §12).

``install → validate → enable → upgrade → disable → remove → migrate`` is the
management envelope (install/enable/disable/remove already exist on
``PluginRegistry``); this module owns the *activation* pipeline the book §12
specifies:

    discover → validate → compatibility → resolve dependencies →
    permission check → register contributions → benchmark gate →
    activate (sandboxed) → health check

Every stage is fail-closed: a failure short-circuits with a stable reason and the
plugin is never marked active. Failures are isolated (no stage raises out of
``activate_plugin``). The legacy ``register_commands`` path is the fallback when a
plugin declares no typed ``contributes`` (compat shim) or when the rollout guard
``contracts_enabled`` is off.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opencontext_core.compat import StrEnum
from opencontext_core.config import PluginHostConfig, SecurityMode
from opencontext_core.plugins.benchmark_gate import BenchmarkRunner, benchmark_gate
from opencontext_core.plugins.compatibility import check_compatibility, runtime_version
from opencontext_core.plugins.extension_points import (
    CONTRIBUTION_ROUTES,
    ExtensionPoint,
)
from opencontext_core.plugins.manifest import PluginManifest
from opencontext_core.plugins.observability import (
    ContributionRecord,
    PluginObserver,
    PluginReceipt,
    build_receipt,
)
from opencontext_core.plugins.sandbox import CapabilityBroker, run_sandboxed
from opencontext_core.registries.base import RegistryMetadata, RegistrySource, TrustLevel


class LifecycleStage(StrEnum):
    """The activation stages, in order."""

    DISCOVER = "discover"
    VALIDATE = "validate"
    COMPATIBILITY = "compatibility"
    RESOLVE_DEPENDENCIES = "resolve_dependencies"
    PERMISSION_CHECK = "permission_check"
    REGISTER_CONTRIBUTIONS = "register_contributions"
    BENCHMARK_GATE = "benchmark_gate"
    ACTIVATE = "activate"
    HEALTH_CHECK = "health_check"


class LifecycleStatus(StrEnum):
    """Terminal status of an activation run."""

    ACTIVE = "active"
    INCOMPATIBLE = "incompatible"
    UNHEALTHY = "unhealthy"
    DISABLED = "disabled"
    FAILED = "failed"


@dataclass
class LifecycleResult:
    """Outcome of an activation run."""

    plugin: str
    status: LifecycleStatus
    stage: LifecycleStage
    reason: str = ""
    contributions: list[ContributionRecord] = field(default_factory=list)
    receipt: PluginReceipt | None = None
    events: list[Any] = field(default_factory=list)
    plugin_obj: Any = None

    @property
    def active(self) -> bool:
        return self.status is LifecycleStatus.ACTIVE


def _plugin_meta(plugin_id: str, point: ExtensionPoint) -> RegistryMetadata:
    """Provenance for a plugin-contributed registry entry (deny-by-default trust)."""
    route = CONTRIBUTION_ROUTES[point]
    return RegistryMetadata(
        source=RegistrySource.PLUGIN,
        trust=TrustLevel.UNTRUSTED,
        plugin_id=plugin_id,
        permissions=[route.permission] if route.permission else [],
    )


def _persona_registrar(plugin_id: str, cid: str) -> Any:
    from opencontext_core.personas.definition import PersonaDefinition

    return PersonaDefinition(id=cid, metadata=_plugin_meta(plugin_id, ExtensionPoint.PERSONAS))


def _skill_registrar(plugin_id: str, cid: str) -> Any:
    from opencontext_core.skills.definition import SkillDefinition

    return SkillDefinition(
        id=cid,
        tier="T2",
        category="Inspection",
        metadata=_plugin_meta(plugin_id, ExtensionPoint.SKILLS),
    )


def _harness_registrar(plugin_id: str, cid: str) -> Any:
    from opencontext_core.harness.definition import HarnessDefinition

    return HarnessDefinition(
        id=cid,
        default_mode="off",
        metadata=_plugin_meta(plugin_id, ExtensionPoint.HARNESSES),
    )


# Points with a concrete in-tree registry the lifecycle can register a provenance-
# stamped definition into. Other points are recorded (observable) but registered
# only when the caller supplies a sink that accepts a raw id.
_REGISTRARS: dict[ExtensionPoint, Callable[[str, str], Any]] = {
    ExtensionPoint.PERSONAS: _persona_registrar,
    ExtensionPoint.SKILLS: _skill_registrar,
    ExtensionPoint.HARNESSES: _harness_registrar,
}


def activate_plugin(
    registry: Any,
    name: str,
    *,
    host_config: PluginHostConfig | None = None,
    core_version: str | None = None,
    min_core_version: str | None = None,
    available_capabilities: set[str] | None = None,
    sinks: dict[ExtensionPoint, Any] | None = None,
    benchmark_runner: BenchmarkRunner | None = None,
    isolation_probe: Callable[[], bool] | None = None,
    observer: PluginObserver | None = None,
    security_mode: SecurityMode = SecurityMode.PRIVATE_PROJECT,
) -> LifecycleResult:
    """Run a plugin through the full activation lifecycle (fail-closed)."""
    cfg = host_config or PluginHostConfig()
    core_version = core_version or runtime_version()
    available_capabilities = available_capabilities or set()
    sinks = sinks or {}
    obs = observer or PluginObserver()
    stages: list[str] = []

    def _result(
        status: LifecycleStatus,
        stage: LifecycleStage,
        reason: str,
        *,
        contributions: list[ContributionRecord] | None = None,
        plugin_obj: Any = None,
        plugin_dir: Path | None = None,
    ) -> LifecycleResult:
        obs.emit_stage(stage.value, name, status=status.value, detail=reason)
        receipt = build_receipt(
            name,
            status=status.value,
            stages=stages,
            contributions=contributions or [],
            reason=reason,
            plugin_dir=plugin_dir,
        )
        return LifecycleResult(
            plugin=name,
            status=status,
            stage=stage,
            reason=reason,
            contributions=contributions or [],
            receipt=receipt,
            events=obs.events,
            plugin_obj=plugin_obj,
        )

    def _advance(stage: LifecycleStage) -> None:
        """Enter a stage: record it and emit an observable event."""
        stages.append(stage.value)
        obs.emit_stage(stage.value, name, status="enter")

    # ── Rollout guard: legacy path when contracts disabled ──────────────────
    if not cfg.contracts_enabled:
        plugin_obj = registry.load(name)
        if plugin_obj is None:
            return _result(LifecycleStatus.FAILED, LifecycleStage.ACTIVATE, "legacy_load_failed")
        return _result(
            LifecycleStatus.ACTIVE, LifecycleStage.ACTIVATE, "legacy_path", plugin_obj=plugin_obj
        )

    # ── Stage 1: discover ───────────────────────────────────────────────────
    _advance(LifecycleStage.DISCOVER)
    info = registry.get_info(name)
    if info is None:
        return _result(LifecycleStatus.FAILED, LifecycleStage.DISCOVER, "not_discovered")
    plugin_dir = Path(registry.plugins_dir) / name

    # ── Stage 2: validate ───────────────────────────────────────────────────
    _advance(LifecycleStage.VALIDATE)
    try:
        raw = json.loads((plugin_dir / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _result(
            LifecycleStatus.FAILED, LifecycleStage.VALIDATE, f"manifest_unreadable: {exc}"
        )
    if not raw.get("enabled", True):
        return _result(LifecycleStatus.DISABLED, LifecycleStage.VALIDATE, "disabled")
    try:
        manifest = PluginManifest.from_plugin_json(raw)
    except Exception as exc:
        return _result(LifecycleStatus.FAILED, LifecycleStage.VALIDATE, f"invalid_manifest: {exc}")

    # ── Stage 3: compatibility ──────────────────────────────────────────────
    _advance(LifecycleStage.COMPATIBILITY)
    compat = check_compatibility(manifest, core_version, min_core_version=min_core_version)
    if not compat.ok:
        return _result(LifecycleStatus.INCOMPATIBLE, LifecycleStage.COMPATIBILITY, compat.reason)

    # ── Stage 4: resolve dependencies ───────────────────────────────────────
    _advance(LifecycleStage.RESOLVE_DEPENDENCIES)
    missing_caps = [c for c in manifest.requires.capabilities if c not in available_capabilities]
    if missing_caps:
        return _result(
            LifecycleStatus.FAILED,
            LifecycleStage.RESOLVE_DEPENDENCIES,
            f"missing_capabilities: {', '.join(missing_caps)}",
        )
    missing_deps = [d for d in manifest.requires.plugins if registry.get_info(d) is None]
    if missing_deps:
        return _result(
            LifecycleStatus.FAILED,
            LifecycleStage.RESOLVE_DEPENDENCIES,
            f"missing_dependencies: {', '.join(missing_deps)}",
        )

    # ── Stage 5: permission check ───────────────────────────────────────────
    _advance(LifecycleStage.PERMISSION_CHECK)
    # Register the declared (deny-by-default) permissions so the broker's
    # ``is_allowed`` checks resolve, then build the broker. A plugin cannot
    # self-grant: the broker routes every capability through the Policy Engine.
    registry.register_declared_permissions(name, manifest.permissions)
    broker = CapabilityBroker(registry, name, security_mode=security_mode)
    _ = broker  # broker is brokered to the activated plugin (kept on the registry)

    # ── Stage 6: register contributions ─────────────────────────────────────
    _advance(LifecycleStage.REGISTER_CONTRIBUTIONS)
    plugin_id = manifest.id or name
    contributions: list[ContributionRecord] = []
    try:
        for point_str, ids in manifest.contributes.items():
            point = ExtensionPoint(point_str)
            registrar = _REGISTRARS.get(point)
            sink = sinks.get(point)
            for cid in ids:
                record = ContributionRecord(
                    plugin_id=plugin_id, extension_point=point.value, contribution_id=cid
                )
                if sink is not None and registrar is not None:
                    sink.register(registrar(plugin_id, cid), replace=True)
                contributions.append(record)
                obs.emit_contribution(record)
    except Exception as exc:
        return _result(
            LifecycleStatus.FAILED,
            LifecycleStage.REGISTER_CONTRIBUTIONS,
            f"registration_failed: {exc}",
            contributions=contributions,
        )

    # ── Stage 7: benchmark gate ─────────────────────────────────────────────
    _advance(LifecycleStage.BENCHMARK_GATE)
    gate = benchmark_gate(manifest, enabled=cfg.benchmark_on_install, runner=benchmark_runner)
    if not gate.passed:
        return _result(
            LifecycleStatus.FAILED,
            LifecycleStage.BENCHMARK_GATE,
            gate.reason,
            contributions=contributions,
            plugin_dir=plugin_dir,
        )

    # ── Stage 8: activate (sandboxed) ───────────────────────────────────────
    _advance(LifecycleStage.ACTIVATE)
    if manifest.contributes.is_empty():
        # Compat shim: a plugin with no typed contributions loads the legacy way.
        plugin_obj = registry.load(name)
        if plugin_obj is None:
            return _result(
                LifecycleStatus.FAILED, LifecycleStage.ACTIVATE, "legacy_load_failed",
                contributions=contributions, plugin_dir=plugin_dir,
            )
    else:
        sandbox = run_sandboxed(
            plugin_dir,
            entry_point=info.entry_point,
            plugin_name=name,
            entry_checksum=raw.get("entry_checksum", ""),
            isolation_probe=isolation_probe,
        )
        if not sandbox.ok:
            return _result(
                LifecycleStatus.FAILED, LifecycleStage.ACTIVATE, sandbox.reason,
                contributions=contributions, plugin_dir=plugin_dir,
            )
        plugin_obj = sandbox.plugin

    # ── Stage 9: health check ───────────────────────────────────────────────
    _advance(LifecycleStage.HEALTH_CHECK)
    healthy, reason = _run_health_check(plugin_obj, contributions, sinks)
    if not healthy:
        return _result(
            LifecycleStatus.UNHEALTHY, LifecycleStage.HEALTH_CHECK, reason,
            contributions=contributions, plugin_obj=plugin_obj, plugin_dir=plugin_dir,
        )

    return _result(
        LifecycleStatus.ACTIVE,
        LifecycleStage.HEALTH_CHECK,
        "activated",
        contributions=contributions,
        plugin_obj=plugin_obj,
        plugin_dir=plugin_dir,
    )


def _run_health_check(
    plugin_obj: Any,
    contributions: list[ContributionRecord],
    sinks: dict[ExtensionPoint, Any],
) -> tuple[bool, str]:
    """Call the plugin's health hook and verify contributions resolve."""
    # 1. Verify each contribution registered into a sink actually resolves.
    for record in contributions:
        point = ExtensionPoint(record.extension_point)
        sink = sinks.get(point)
        registrar = _REGISTRARS.get(point)
        if sink is not None and registrar is not None and not sink.has(record.contribution_id):
            return False, f"contribution_unresolved: {record.contribution_id}"
    # 2. Call an explicit health() hook when present.
    health = getattr(plugin_obj, "health", None)
    if callable(health):
        try:
            if not health():
                return False, "health_check_failed"
        except Exception as exc:
            return False, f"health_check_error: {exc}"
        return True, "healthy"
    # 3. Otherwise best-effort initialize().
    initialize = getattr(plugin_obj, "initialize", None)
    if callable(initialize):
        try:
            initialize({})
        except Exception as exc:
            return False, f"initialize_error: {exc}"
    return True, "healthy"
