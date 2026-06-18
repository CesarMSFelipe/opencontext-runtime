"""Deep diagnostics — comprehensive system health assessment.

Integrates verification checks, component health, system info, plugins,
and update status into a single consolidated report. Used by
``opencontext doctor deep``.
"""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from opencontext_core.config import OpenContextConfig
from opencontext_core.doctor.component_checks import ComponentDoctor
from opencontext_core.state import StateStore
from opencontext_core.update import UpdateChecker
from opencontext_core.user_prefs import UserConfigStore
from opencontext_core.verification import run_all_checks

# ── Data Model ──────────────────────────────────────────────────────────────


@dataclass
class DeepDiagnostic:
    """A single diagnostic finding."""

    name: str
    status: str  # passed | warning | failed | info | error
    message: str
    details: str = ""
    recommendation: str | None = None


@dataclass
class DeepReport:
    """Consolidated deep diagnostics report."""

    timestamp: str
    system: list[DeepDiagnostic] = field(default_factory=list)
    verification: list[DeepDiagnostic] = field(default_factory=list)
    components: list[DeepDiagnostic] = field(default_factory=list)
    plugins: list[DeepDiagnostic] = field(default_factory=list)
    update: list[DeepDiagnostic] = field(default_factory=list)
    config: list[DeepDiagnostic] = field(default_factory=list)

    @property
    def all_checks(self) -> list[DeepDiagnostic]:
        return (
            self.system
            + self.verification
            + self.components
            + self.plugins
            + self.update
            + self.config
        )

    @property
    def passed(self) -> int:
        return sum(1 for d in self.all_checks if d.status == "passed")

    @property
    def warnings(self) -> int:
        return sum(1 for d in self.all_checks if d.status == "warning")

    @property
    def failures(self) -> int:
        return sum(1 for d in self.all_checks if d.status in ("failed", "error"))

    @property
    def is_healthy(self) -> bool:
        return self.failures == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "healthy": self.is_healthy,
            "summary": {
                "total": len(self.all_checks),
                "passed": self.passed,
                "warnings": self.warnings,
                "failures": self.failures,
            },
            "sections": {
                "system": [self._diag_to_dict(d) for d in self.system],
                "verification": [self._diag_to_dict(d) for d in self.verification],
                "components": [self._diag_to_dict(d) for d in self.components],
                "plugins": [self._diag_to_dict(d) for d in self.plugins],
                "update": [self._diag_to_dict(d) for d in self.update],
                "config": [self._diag_to_dict(d) for d in self.config],
            },
        }

    @staticmethod
    def _diag_to_dict(d: DeepDiagnostic) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": d.name,
            "status": d.status,
            "message": d.message,
        }
        if d.details:
            result["details"] = d.details
        if d.recommendation:
            result["recommendation"] = d.recommendation
        return result


# ── System Info ─────────────────────────────────────────────────────────────


def _collect_system_info() -> list[DeepDiagnostic]:
    """Collect OS, Python, and hardware diagnostics."""
    diagnostics: list[DeepDiagnostic] = []

    # OS info
    diagnostics.append(
        DeepDiagnostic(
            name="os.platform",
            status="info",
            message=f"{sys.platform} / {platform.platform()}",
            details=f"Architecture: {platform.machine()} | "
            f"Processor: {platform.processor() or 'unknown'}",
        )
    )

    # Python info
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_impl = platform.python_implementation()
    ok = sys.version_info >= (3, 12)
    diagnostics.append(
        DeepDiagnostic(
            name="python.version",
            status="passed" if ok else "warning",
            message=f"{py_impl} {py_ver}",
            details=f"Executable: {sys.executable}",
            recommendation=None if ok else "Python 3.12+ recommended",
        )
    )

    # CPU count
    cpus = os.cpu_count() or 0
    diagnostics.append(
        DeepDiagnostic(
            name="system.cpu",
            status="info",
            message=f"{cpus} logical CPU(s)",
        )
    )

    # Config directory
    config_dir = UserConfigStore.CONFIG_DIR
    config_ok = config_dir.exists()
    diagnostics.append(
        DeepDiagnostic(
            name="system.config_dir",
            status="passed" if config_ok else "warning",
            message=str(config_dir),
            details="Exists" if config_ok else "Not created yet",
        )
    )

    # Disk space on config volume
    try:
        import shutil

        usage = shutil.disk_usage(config_dir if config_dir.exists() else Path.home())
        free_gb = usage.free / (1024**3)
        diagnostics.append(
            DeepDiagnostic(
                name="system.disk",
                status="passed" if free_gb >= 0.5 else "warning",
                message=f"{free_gb:.1f} GB free",
                details=f"Total: {usage.total / (1024**3):.1f} GB",
                recommendation=None if free_gb >= 0.5 else "Free up disk space for indexing",
            )
        )
    except Exception as exc:
        diagnostics.append(
            DeepDiagnostic(
                name="system.disk",
                status="warning",
                message=f"Cannot check disk: {exc}",
            )
        )

    # PATH info
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    diagnostics.append(
        DeepDiagnostic(
            name="system.path_entries",
            status="info",
            message=f"{len(path_dirs)} directories in PATH",
        )
    )

    return diagnostics


# ── Config Section ──────────────────────────────────────────────────────────


def _collect_config_info(config: OpenContextConfig) -> list[DeepDiagnostic]:
    """Collect configuration diagnostics."""
    diagnostics: list[DeepDiagnostic] = []

    # Security mode
    mode = config.security.mode.value
    diagnostics.append(
        DeepDiagnostic(
            name="config.security_mode",
            status="info",
            message=f"Security mode: {mode}",
            details=(
                f"External providers: "
                f"{'enabled' if config.security.external_providers_enabled else 'disabled'}"
            ),
        )
    )

    # Tools
    mcp_enabled = config.tools.mcp.enabled
    native_enabled = config.tools.native.enabled
    diagnostics.append(
        DeepDiagnostic(
            name="config.tools",
            status="passed" if not (mcp_enabled or native_enabled) else "warning",
            message=(
                f"MCP: {'on' if mcp_enabled else 'off'}, "
                f"Native: {'on' if native_enabled else 'off'}"
            ),
            recommendation=(
                "Both tools off is safest. Enable only what you need."
                if mcp_enabled or native_enabled
                else None
            ),
        )
    )

    prefs = UserConfigStore().load()
    features_on = sum(
        1
        for f in ["knowledge_graph", "mcp_server", "git_integration", "call_graph"]
        if getattr(prefs.features, f, False)
    )
    diagnostics.append(
        DeepDiagnostic(
            name="config.features",
            status="info",
            message=f"{features_on} features enabled",
            details=f"KG: {prefs.features.knowledge_graph}, "
            f"MCP: {prefs.features.mcp_server}, "
            f"Git: {prefs.features.git_integration}",
        )
    )

    # SDD config
    diagnostics.append(
        DeepDiagnostic(
            name="config.sdd",
            status="info",
            message=f"SDD interactive: {config.sdd.interactive} | "
            f"Delivery: {config.sdd.delivery_strategy.value}",
        )
    )

    return diagnostics


# ── Verification Adapter ────────────────────────────────────────────────────


_STATUS_MAP = {
    "passed": "passed",
    "warning": "warning",
    "failed": "failed",
    "skipped": "info",
    "error": "error",
}


def _from_verification_report() -> list[DeepDiagnostic]:
    """Convert verification checks to deep diagnostics."""
    report = run_all_checks()
    return [
        DeepDiagnostic(
            name=f"verify.{r.name.lower().replace(' ', '_')}",
            status=_STATUS_MAP.get(r.status, "info"),
            message=r.message,
            details=r.details,
        )
        for r in report.results
    ]


# ── Component Doctor Adapter ────────────────────────────────────────────────


def _from_component_doctor(config: OpenContextConfig) -> list[DeepDiagnostic]:
    """Convert component health checks to deep diagnostics."""
    doctor = ComponentDoctor(config)
    checks = doctor.check_all()
    return [
        DeepDiagnostic(
            name=f"component.{c.name}",
            status="passed" if c.ok else ("warning" if c.status == "warning" else "failed"),
            message=c.details,
            details=f"Status: {c.status}",
            recommendation=c.recommendation,
        )
        for c in checks
    ]


# ── Plugin Section ──────────────────────────────────────────────────────────


def _from_plugins() -> list[DeepDiagnostic]:
    """Collect plugin diagnostics."""
    diagnostics: list[DeepDiagnostic] = []

    from opencontext_core.plugin_system import PluginRegistry

    registry = PluginRegistry()
    plugins = registry.discover()
    if not plugins:
        diagnostics.append(
            DeepDiagnostic(
                name="plugins.total",
                status="info",
                message="No plugins installed",
            )
        )
        return diagnostics

    enabled = [p for p in plugins if p.enabled]
    disabled = [p for p in plugins if not p.enabled]
    diagnostics.append(
        DeepDiagnostic(
            name="plugins.total",
            status="passed",
            message=f"{len(enabled)} enabled, {len(disabled)} disabled",
        )
    )

    # Plugin details
    for p in enabled:
        source = getattr(p, "install_source", "local") or "local"
        diagnostics.append(
            DeepDiagnostic(
                name=f"plugin.{p.name}",
                status="passed",
                message=f"{p.name} v{p.version or '?'}",
                details=f"Source: {source} | Installed: {getattr(p, 'installed_at', '?')}",
            )
        )

    try:
        from opencontext_core.plugin_system import PluginUpdater

        updater = PluginUpdater()
        updates = updater.check_updates()
        for update in updates:
            if update.status in ("updated", "installed"):
                diagnostics.append(
                    DeepDiagnostic(
                        name=f"plugin_update.{update.name}",
                        status="warning",
                        message=f"{update.name}: {update.version}",
                        recommendation=f"Run 'opencontext plugin update {p.name}'",
                    )
                )
    except Exception as exc:
        diagnostics.append(
            DeepDiagnostic(
                name="plugin_updates",
                status="warning",
                message=f"Cannot check updates: {exc}",
            )
        )

    return diagnostics


# ── Update Section ──────────────────────────────────────────────────────────


def _from_updates() -> list[DeepDiagnostic]:
    """Collect update diagnostics."""
    diagnostics: list[DeepDiagnostic] = []

    checker = UpdateChecker()
    try:
        result = checker.check()
        if result.is_outdated:
            diagnostics.append(
                DeepDiagnostic(
                    name="update.available",
                    status="warning",
                    message=(
                        f"v{result.latest_version} available (current: v{result.current_version})"
                    ),
                    recommendation="Run 'opencontext upgrade'",
                )
            )
        else:
            diagnostics.append(
                DeepDiagnostic(
                    name="update.available",
                    status="passed",
                    message=f"v{result.current_version} is up to date",
                    details=f"Last checked: {result.checked_at}",
                )
            )
    except Exception as exc:
        diagnostics.append(
            DeepDiagnostic(
                name="update.available",
                status="warning",
                message=f"Cannot check: {exc}",
            )
        )

    # State sync info
    state = StateStore.load()
    if state.last_sync:
        diagnostics.append(
            DeepDiagnostic(
                name="state.last_sync",
                status="info",
                message=f"Last sync: {state.last_sync}",
            )
        )
    if state.last_verified:
        diagnostics.append(
            DeepDiagnostic(
                name="state.last_verified",
                status="info",
                message=f"Last verified: {state.last_verified}",
            )
        )
    if state.last_update_check:
        diagnostics.append(
            DeepDiagnostic(
                name="state.last_update_check",
                status="info",
                message=f"Last update check: {state.last_update_check}",
            )
        )

    return diagnostics


# ── Main Entry Point ────────────────────────────────────────────────────────


def run_deep_diagnostics(config: OpenContextConfig) -> DeepReport:
    """Run all deep diagnostics and return a consolidated report.

    Args:
        config: The current OpenContext configuration.

    Returns:
        A DeepReport with all diagnostic sections populated.
    """
    report = DeepReport(timestamp=datetime.now().isoformat())
    report.system = _collect_system_info()
    report.config = _collect_config_info(config)
    report.verification = _from_verification_report()
    report.components = _from_component_doctor(config)
    report.plugins = _from_plugins()
    report.update = _from_updates()

    try:
        state = StateStore.load()
        state.last_verified = report.timestamp
        StateStore.save(state)
    except Exception:
        pass

    return report
