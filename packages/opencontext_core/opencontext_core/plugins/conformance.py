"""SDK conformance test suite (PR-015, doc 60 item 14, book §37 Validation).

A conformance suite a plugin (or the SDK's ``validate`` command) runs to prove it
honors the public contracts before activation. Each check is machine-checkable
(book §37 core principle 8) and maps to a contract invariant. The suite is pure:
it inspects a manifest (and optionally the entry module) and returns a report; it
performs no activation and no IO.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from opencontext_core.plugins.compatibility import check_compatibility
from opencontext_core.plugins.contracts import CONTRACTS
from opencontext_core.plugins.extension_points import CONTRIBUTION_ROUTES, ExtensionPoint
from opencontext_core.plugins.manifest import PLUGIN_SCHEMA_VERSION, PluginManifest


@dataclass(frozen=True)
class ConformanceCheck:
    """One conformance check result."""

    id: str
    passed: bool
    detail: str


@dataclass
class ConformanceReport:
    """Aggregate conformance report for a plugin manifest."""

    plugin: str
    checks: list[ConformanceCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[ConformanceCheck]:
        return [c for c in self.checks if not c.passed]


def run_conformance(
    manifest: PluginManifest,
    *,
    core_version: str | None = None,
) -> ConformanceReport:
    """Run the conformance suite over ``manifest`` and return a report.

    Checks (book §37 / §12 invariants):
    - CONF-1 schema_version is the supported plugin schema.
    - CONF-2 a stable plugin id is declared.
    - CONF-3 every contributed extension point resolves to a public contract.
    - CONF-4 Studio-panel contributions are read-only (no mutation permission).
    - CONF-5 requires.runtime is parseable.
    - CONF-6 (when ``core_version`` given) the plugin is compatible.
    """
    name = manifest.id or manifest.name
    checks: list[ConformanceCheck] = []

    checks.append(
        ConformanceCheck(
            "CONF-1",
            manifest.schema_version == PLUGIN_SCHEMA_VERSION,
            f"schema_version={manifest.schema_version!r}",
        )
    )
    checks.append(
        ConformanceCheck(
            "CONF-2",
            bool(manifest.id),
            "plugin id declared" if manifest.id else "missing plugin id",
        )
    )

    # CONF-3: every contributed point binds to a public contract.
    unresolved: list[str] = []
    for point_str, _ids in manifest.contributes.items():
        point = ExtensionPoint(point_str)
        route = CONTRIBUTION_ROUTES[point]
        if route.contract not in CONTRACTS:
            unresolved.append(point_str)
    checks.append(
        ConformanceCheck(
            "CONF-3",
            not unresolved,
            "all contributions bind to a public contract"
            if not unresolved
            else f"no contract for: {', '.join(unresolved)}",
        )
    )

    # CONF-4: Studio panels are read-only — a panel-only plugin must not require a
    # mutation permission (book §37: panels cannot execute Runtime operations).
    panels = manifest.contributes.studio_panels
    mutation_perms = bool(
        manifest.permissions.kg_write or manifest.permissions.memory_write
    )
    panel_only = bool(panels) and not _has_non_panel_contributions(manifest)
    panel_ok = not (panel_only and mutation_perms)
    checks.append(
        ConformanceCheck(
            "CONF-4",
            panel_ok,
            "studio panels read-only"
            if panel_ok
            else "panel-only plugin declares mutation permissions",
        )
    )

    # CONF-5: requires.runtime parseable.
    runtime_ok = True
    try:
        check_compatibility(manifest, "1.0.0")
    except Exception:
        runtime_ok = False
    checks.append(
        ConformanceCheck("CONF-5", runtime_ok, f"requires.runtime={manifest.requires.runtime!r}")
    )

    # CONF-6: compatibility (optional).
    if core_version is not None:
        compat = check_compatibility(manifest, core_version)
        checks.append(ConformanceCheck("CONF-6", compat.ok, compat.reason))

    return ConformanceReport(plugin=name, checks=checks)


def _has_non_panel_contributions(manifest: PluginManifest) -> bool:
    """True when the plugin contributes more than just Studio panels.

    A plugin that also contributes a KG/memory provider legitimately needs
    mutation permissions; the read-only rule applies to panel-only plugins.
    """
    for point_str, _ids in manifest.contributes.items():
        if point_str != ExtensionPoint.STUDIO_PANELS.value:
            return True
    return False
