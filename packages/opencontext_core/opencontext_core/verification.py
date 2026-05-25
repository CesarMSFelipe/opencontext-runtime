"""Verification system — component-specific health checks.

After setup or sync, run these checks to verify everything is working.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from opencontext_core.state import StateStore
from opencontext_core.user_prefs import UserConfigStore


def _opencode_mcp_paths() -> list[Path]:
    """Platform-appropriate OpenCode MCP config paths."""
    paths: list[Path] = []
    home = Path.home()
    # Linux / macOS (.config convention)
    paths.append(home / ".config" / "opencode" / "mcp.json")
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        paths.append(appdata / "opencode" / "mcp.json")
        paths.append(home / "AppData" / "Roaming" / "opencode" / "mcp.json")
    elif sys.platform == "darwin":
        paths.append(home / "Library" / "Application Support" / "opencode" / "mcp.json")
    return paths


@dataclass
class CheckResult:
    """Result of a single verification check."""

    name: str
    status: str  # "passed", "warning", "failed", "skipped"
    message: str
    details: str = ""


@dataclass
class VerificationReport:
    """Complete verification report."""

    results: list[CheckResult] = field(default_factory=list)
    timestamp: str = ""

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "passed")

    @property
    def warnings(self) -> int:
        return sum(1 for r in self.results if r.status == "warning")

    @property
    def failures(self) -> int:
        return sum(1 for r in self.results if r.status == "failed")

    @property
    def is_healthy(self) -> bool:
        return self.failures == 0


# ── Individual Checks ──────────────────────────────────────────────────────


def check_python_version() -> CheckResult:
    """Verify Python 3.12+."""

    import sys

    major, minor = sys.version_info[:2]
    if major >= 3 and minor >= 12:
        return CheckResult(
            "Python Version", "passed", f"Python {major}.{minor}.{sys.version_info[2]}"
        )
    return CheckResult("Python Version", "warning", f"Python {major}.{minor} < 3.12 recommended")


def check_user_config() -> CheckResult:
    """Verify user config exists and is valid."""

    store = UserConfigStore()
    path = store.CONFIG_FILE
    if not path.exists():
        return CheckResult(
            "User Config", "warning", "No config yet — run 'opencontext config wizard'"
        )

    try:
        prefs = store.load()
        return CheckResult(
            "User Config", "passed", f"Config at {path}", f"Mode: {prefs.security_mode}"
        )
    except Exception as e:
        return CheckResult("User Config", "failed", f"Corrupted config: {e}")


def check_knowledge_graph() -> CheckResult:
    """Verify KG database exists."""

    prefs = UserConfigStore().load()
    if not prefs.features.knowledge_graph:
        return CheckResult("Knowledge Graph", "skipped", "Not enabled")

    db_path = Path(prefs.custom_storage_path) / "codegraph.db"
    if not db_path.exists():
        return CheckResult(
            "Knowledge Graph",
            "warning",
            "No database yet — run 'opencontext index .'",
            f"Expected at: {db_path.resolve()}",
        )

    try:
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM files")
        file_count = cursor.fetchone()[0]
        conn.close()
        return CheckResult("Knowledge Graph", "passed", f"Database with {file_count} indexed files")
    except Exception as e:
        return CheckResult("Knowledge Graph", "failed", f"Database error: {e}")


def check_mcp_config() -> CheckResult:
    """Verify MCP configuration."""

    prefs = UserConfigStore().load()
    if not prefs.features.mcp_server:
        return CheckResult("MCP Server", "skipped", "Not enabled")

    # Check OpenCode MCP config across platform paths
    import json

    for mcp_path in _opencode_mcp_paths():
        if mcp_path.exists():
            try:
                config = json.loads(mcp_path.read_text(encoding="utf-8"))
                if "mcpServers" in config and "opencontext" in config["mcpServers"]:
                    return CheckResult("MCP Server", "passed", f"Configured at {mcp_path}")
                return CheckResult(
                    "MCP Server", "warning", "MCP config exists but opencontext entry missing"
                )
            except Exception:
                return CheckResult("MCP Server", "warning", "MCP config exists but invalid")
    return CheckResult("MCP Server", "warning", "Not configured — use 'opencontext install'")


def check_plugins() -> CheckResult:
    """Verify installed plugins."""

    from opencontext_core.plugin_system import PluginRegistry

    registry = PluginRegistry()
    plugins = registry.discover()
    if not plugins:
        return CheckResult("Plugins", "skipped", "No plugins installed")

    enabled = [p.name for p in plugins if p.enabled]
    disabled = [p.name for p in plugins if not p.enabled]

    msg = f"{len(enabled)} enabled"
    if disabled:
        msg += f", {len(disabled)} disabled: {', '.join(disabled)}"
    return CheckResult("Plugins", "passed", msg)


def check_state() -> CheckResult:
    """Verify state tracking."""

    state = StateStore.load()
    total = len(state.components)
    if total == 0:
        return CheckResult("Installation State", "warning", "No components tracked")

    details = []
    for _cid, cs in state.components.items():
        details.append(f"{cs.name}: {'on' if cs.enabled else 'off'}")
    return CheckResult(
        "Installation State", "passed", f"{total} components tracked", "; ".join(details)
    )


def check_disk_space() -> CheckResult:
    """Verify sufficient disk space."""

    import shutil

    storage_path = Path(UserConfigStore().load().custom_storage_path)
    if storage_path.exists():
        usage = shutil.disk_usage(storage_path)
        free_gb = usage.free / (1024**3)
        if free_gb < 0.1:
            return CheckResult(
                "Disk Space", "warning", f"Only {free_gb:.1f} GB free — may affect indexing"
            )
        return CheckResult("Disk Space", "passed", f"{free_gb:.1f} GB free")
    return CheckResult("Disk Space", "skipped", "Storage not yet created")


def check_harness_phases() -> CheckResult:
    """Verify all 6 SDD harness phases are available."""

    try:
        from opencontext_core.harness.phases import (
            ApplyPhase,
            ArchivePhase,
            ExplorePhase,
            ProposePhase,
            ReviewPhase,
            VerifyPhase,
        )

        phases = {
            "explore": ExplorePhase,
            "propose": ProposePhase,
            "apply": ApplyPhase,
            "verify": VerifyPhase,
            "review": ReviewPhase,
            "archive": ArchivePhase,
        }
        missing = [name for name, cls in phases.items() if cls is None]
        if missing:
            return CheckResult(
                "Harness Phases",
                "warning",
                f"Missing phases: {', '.join(missing)}",
            )

        # Verify each phase has an id attribute
        phase_ids = {
            "explore": ExplorePhase.id,
            "propose": ProposePhase.id,
            "apply": ApplyPhase.id,
            "verify": VerifyPhase.id,
            "review": ReviewPhase.id,
            "archive": ArchivePhase.id,
        }
        return CheckResult(
            "Harness Phases",
            "passed",
            f"6/6 phases available: {', '.join(f'{k}={v}' for k, v in phase_ids.items())}",
        )
    except ImportError as exc:
        return CheckResult("Harness Phases", "failed", f"Import error: {exc}")
    except Exception as exc:
        return CheckResult("Harness Phases", "failed", f"Check error: {exc}")


def check_harness_runner() -> CheckResult:
    """Verify HarnessRunner can be instantiated."""

    try:
        from pathlib import Path

        from opencontext_core.harness.runner import HarnessRunner

        runner = HarnessRunner(root=Path.cwd())
        state = runner.create_run("verify-check", "health check")
        if state and state.run_id:
            return CheckResult(
                "Harness Runner",
                "passed",
                f"Runner ready, sample run_id: {state.run_id[:16]}",
            )
        return CheckResult("Harness Runner", "warning", "Runner created but no run_id")
    except ImportError as exc:
        return CheckResult("Harness Runner", "failed", f"Import error: {exc}")
    except Exception as exc:
        return CheckResult("Harness Runner", "failed", f"Check error: {exc}")


def check_adapters() -> CheckResult:
    """Verify adapter availability.

    Checks that LocalAdapter, PythonAdapter, and AiderAdapter
    are importable and their availability can be queried.
    """

    try:
        from opencontext_core.adapters.aider import AiderAdapter
        from opencontext_core.adapters.local import LocalAdapter, PythonAdapter

        local = LocalAdapter()
        python = PythonAdapter()
        aider = AiderAdapter()

        local_ok = local.check_available()
        python_ok = python.check_available()
        aider_ok = aider.check_available()

        details_parts = []
        details_parts.append(f"local={'✓' if local_ok else '✗'}")
        details_parts.append(f"python={'✓' if python_ok else '✗'}")
        details_parts.append(f"aider={'✓' if aider_ok else '—'}")
        details = ", ".join(details_parts)

        if local_ok and python_ok:
            return CheckResult("Adapters", "passed", f"Core adapters ready ({details})")
        return CheckResult(
            "Adapters",
            "warning",
            f"Some adapters unavailable ({details})",
        )
    except ImportError as exc:
        return CheckResult("Adapters", "failed", f"Import error: {exc}")
    except Exception as exc:
        return CheckResult("Adapters", "failed", f"Check error: {exc}")


def check_boundary_service() -> CheckResult:
    """Verify BoundaryService and AdapterRequest are importable.

    Does NOT run a workflow — only validates that the service can be
    instantiated and build a valid request model.
    """

    try:
        from opencontext_core.adapters.boundary import (
            AdapterRequest,
            AdapterTarget,
            BoundaryService,
        )

        service = BoundaryService()
        assert service.root is not None, "BoundaryService must have a root"

        # Validate request model construction (no dispatch)
        req = AdapterRequest(
            target=AdapterTarget.OPENCODE,
            task="health check",
            root=str(service.root),
            budget_mode="off",
        )
        assert req.target == AdapterTarget.OPENCODE
        assert req.task == "health check"

        return CheckResult(
            "Boundary Service",
            "passed",
            f"Service ready, accepts {len(AdapterTarget)} targets",
        )
    except ImportError as exc:
        return CheckResult("Boundary Service", "failed", f"Import error: {exc}")
    except Exception as exc:
        return CheckResult("Boundary Service", "failed", f"Check error: {exc}")


# ── Registry ───────────────────────────────────────────────────────────────

CHECK_REGISTRY: list[tuple[str, Callable[[], CheckResult], str]] = [
    ("Python Version", check_python_version, "Runtime"),
    ("User Config", check_user_config, "Configuration"),
    ("Knowledge Graph", check_knowledge_graph, "Features"),
    ("MCP Server", check_mcp_config, "Integration"),
    ("Plugins", check_plugins, "Plugins"),
    ("Installation State", check_state, "State"),
    ("Disk Space", check_disk_space, "System"),
    ("Harness Phases", check_harness_phases, "Workflow"),
    ("Harness Runner", check_harness_runner, "Workflow"),
    ("Adapters", check_adapters, "Integration"),
    ("Boundary Service", check_boundary_service, "Integration"),
]


def run_all_checks() -> VerificationReport:
    """Run all verification checks."""

    from datetime import datetime

    report = VerificationReport(timestamp=datetime.now().isoformat())

    for name, check_fn, category in CHECK_REGISTRY:
        try:
            result = check_fn()
        except Exception as e:
            result = CheckResult(name, "failed", f"Check error: {e}")
        result.details = f"[{category}] {result.details}" if result.details else f"[{category}]"
        report.results.append(result)

    # Mark in state
    if report.is_healthy:
        try:
            StateStore.mark_verified()
        except Exception:
            pass

    return report
