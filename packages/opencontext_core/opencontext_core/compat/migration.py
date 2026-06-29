"""Migration-state ledger for the Legacy <-> Runtime vNext transition (PR-000.0).

This module is governance data, not execution code. It records, for every legacy
module being superseded by the Runtime vNext program (PR-001..017), its current
``MigrationState``, the PR that supersedes it, the gating ``runtime.*`` flag, and
the milestone at which the legacy path may be removed.

It also encodes the machine-checkable "migrated" criteria (SPEC CL-006): a module
is ``migrated`` only when all four conditions hold:

    (a) its behaviour is reachable only through the vNext contract,
    (b) the legacy path is removed or shimmed,
    (c) parity tests exist,
    (d) no other module imports the legacy symbol directly.

Conditions (a) and (b) are governance facts recorded on the ledger entry (PR-000.0
cannot dynamically verify "vNext-only reach" before the vNext subsystems exist).
Condition (c) is checked against the recorded parity test (existence-verified when a
repo root is supplied). Condition (d) is computed by a best-effort ``ast`` scan over
the package -- the rule the deferred PR-017 release-gate lint will later enforce
repo-wide (SPEC CL-013).
"""

from __future__ import annotations

import ast
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

# The package this ledger governs: ``.../opencontext_core/``. ``parents[1]`` is the
# package directory (compat/ -> opencontext_core/).
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class MigrationState(StrEnum):
    """Lifecycle of a legacy module through the vNext migration."""

    legacy = "legacy"  # only the legacy path exists
    adapted = "adapted"  # a vNext adapter exists behind a flag; legacy still default
    migrated = "migrated"  # vNext-only reach; legacy shimmed; parity green; no direct importers
    removed = "removed"  # legacy module deleted


class ModuleMigration(BaseModel):
    """One legacy module's declared migration state."""

    model_config = ConfigDict(extra="forbid")

    module: str  # repo-relative path, e.g. "harness/runner.py"
    legacy_symbol: str  # e.g. "HarnessRunner"
    state: MigrationState = MigrationState.legacy
    superseded_by: str | None = None  # owning PR, e.g. "PR-003"
    removal_milestone: str | None = None  # e.g. "milestone-C"
    flag: str | None = None  # gating runtime.* flag, e.g. "runtime.registry_enabled"
    # Governance facts feeding the "migrated" predicate (CL-006 a/b):
    vnext_only: bool = False  # (a) reachable only through the vNext contract
    legacy_shimmed: bool = False  # (b) legacy path removed or shimmed
    parity_test: str | None = None  # (c) repo-relative path to the parity test


class TwoSpineDecision(BaseModel):
    """Recorded resolution of the two execution spines (SPEC CL-008)."""

    model_config = ConfigDict(extra="forbid")

    chosen_spine: str
    adapted_spine: str
    adapted_spine_state: MigrationState = MigrationState.adapted
    removal_milestone: str
    rationale: str


# The convergence decision: HarnessRunner->RuntimeApi is the vNext spine; the
# narrower, later OcNewConductor is adapted onto it and scheduled for removal once
# resume carry-over parity is proven.
TWO_SPINE_CONVERGENCE = TwoSpineDecision(
    chosen_spine="HarnessRunner->RuntimeApi",
    adapted_spine="OcNewConductor",
    adapted_spine_state=MigrationState.adapted,
    removal_milestone="milestone-C",
    rationale=(
        "RuntimeApi already brackets HarnessRunner.run() (runtime/api.py), so it is "
        "the proven spine. OcNewConductor is the narrower, later spine; it is adapted "
        "onto RuntimeApi and removed only after its resume carry-over behaviour reaches "
        "parity on the HarnessRunner spine."
    ),
)


class MigrationLedger(BaseModel):
    """Per-module migration-state ledger, persisted as a machine-readable artifact."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.migration_ledger.v1"
    modules: list[ModuleMigration] = Field(default_factory=list)
    convergence: TwoSpineDecision = TWO_SPINE_CONVERGENCE

    def get(self, module: str) -> ModuleMigration | None:
        """Return the entry for *module*, or ``None`` if it is unclassified."""
        for entry in self.modules:
            if entry.module == module:
                return entry
        return None

    def states(self) -> dict[str, MigrationState]:
        """Map every classified module to its single migration state."""
        return {entry.module: entry.state for entry in self.modules}

    def is_migrated(self, module: str, *, root: Path | str | None = None) -> tuple[bool, list[str]]:
        """Evaluate the four CL-006 "migrated" conditions for *module*.

        Returns ``(migrated, reasons)`` where ``reasons`` names each failing
        condition. An unknown module is not migrated.
        """
        entry = self.get(module)
        if entry is None:
            return False, [f"module not in ledger: {module}"]
        return _evaluate_migrated(entry, root=root)

    def to_markdown(self) -> str:
        """Render the ledger as the machine-readable docs mirror table."""
        header = (
            "| Module | Legacy symbol | State | Superseded by | Flag | Removal |\n"
            "|--------|---------------|-------|---------------|------|---------|"
        )
        rows = [
            "| {module} | {sym} | {state} | {pr} | {flag} | {removal} |".format(
                module=e.module,
                sym=e.legacy_symbol,
                state=e.state.value,
                pr=e.superseded_by or "-",
                flag=e.flag or "-",
                removal=e.removal_milestone or "-",
            )
            for e in self.modules
        ]
        return "\n".join([header, *rows])


def is_migrated(
    module: str, *, root: Path | str | None = None, ledger: MigrationLedger | None = None
) -> tuple[bool, list[str]]:
    """Module-level convenience for ``MigrationLedger.is_migrated`` (SPEC CL-006).

    Evaluates the four "migrated" conditions for *module* against *ledger*
    (defaults to the seeded ``MIGRATION_LEDGER``) and returns
    ``(migrated, reasons)`` naming each failing condition.
    """
    return (ledger or MIGRATION_LEDGER).is_migrated(module, root=root)


def _evaluate_migrated(
    entry: ModuleMigration, *, root: Path | str | None
) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    # (a) reachable only through the vNext contract
    if not entry.vnext_only:
        reasons.append("(a) not reachable only via the vNext contract")

    # (b) legacy path removed or shimmed
    if not entry.legacy_shimmed:
        reasons.append("(b) legacy path not removed/shimmed")

    # (c) parity tests exist (existence-verified when a repo root is given)
    if entry.parity_test is None:
        reasons.append("(c) no parity test recorded")
    elif root is not None and not (Path(root) / entry.parity_test).exists():
        reasons.append(f"(c) parity test not found: {entry.parity_test}")

    # (d) no module imports the legacy symbol directly (best-effort ast scan)
    importers = direct_legacy_importers(entry.module, entry.legacy_symbol)
    if importers:
        shown = ", ".join(importers[:5])
        more = "" if len(importers) <= 5 else f" (+{len(importers) - 5} more)"
        reasons.append(f"(d) {len(importers)} direct legacy importer(s): {shown}{more}")

    return (not reasons), reasons


def _module_to_dotted(module: str) -> str:
    """``"harness/runner.py"`` -> ``"harness.runner"`` (drop trailing ``__init__``)."""
    rel = module[:-3] if module.endswith(".py") else module
    parts = [p for p in rel.split("/") if p]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def direct_legacy_importers(
    module: str, legacy_symbol: str, *, package_root: Path | None = None
) -> list[str]:
    """Return package files that import *legacy_symbol* from *module* (CL-006 d).

    Best-effort static check via ``ast``. Skips the legacy module's own file, the
    compat package itself (it is allowed to reference legacy symbols), and any file
    that fails to parse.
    """
    root = package_root or _PACKAGE_ROOT
    dotted = _module_to_dotted(module)
    own_file = (root / module).resolve()
    importers: list[str] = []

    for path in sorted(root.rglob("*.py")):
        resolved = path.resolve()
        if resolved == own_file:
            continue
        if "compat" in path.relative_to(root).parts:
            continue
        try:
            tree = ast.parse(resolved.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        if _imports_symbol(tree, dotted, legacy_symbol):
            importers.append(str(path.relative_to(root)))

    return importers


def _imports_symbol(tree: ast.Module, dotted: str, symbol: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == dotted or node.module.endswith("." + dotted):
                if any(alias.name == symbol for alias in node.names):
                    return True
    return False


# --------------------------------------------------------------------- seeded ledger
# Seeded from the live repo + the program build status
# (.sdd/changes/_INDEX-refined-runtime-vnext.md): PRs 001/000/003/000.1/002/005/
# 000.2/006/004/007 are DONE; 008..017 + 000.3/000.4 are PENDING. A module whose
# superseding adapter has shipped is ``adapted`` (legacy still default behind its
# flag); a module whose superseding PR is pending is ``legacy``.
MIGRATION_LEDGER = MigrationLedger(
    modules=[
        # Compat-debt #0: the folded legacy runtime facade (PR-001).
        ModuleMigration(
            module="runtime/__init__.py",
            legacy_symbol="OpenContextRuntime",
            state=MigrationState.adapted,
            superseded_by="PR-001",
            removal_milestone="milestone-B",
            flag="runtime.session_wrapper",
            vnext_only=False,
            legacy_shimmed=True,
            parity_test="tests/runtime/test_compat_wrapper.py",
        ),
        # CL-008 two-spine: HarnessRunner is the adopted spine (reached via RuntimeApi);
        # its WORKFLOW_TRACKS scheduling is superseded by the PR-003 registry.
        ModuleMigration(
            module="harness/runner.py",
            legacy_symbol="HarnessRunner",
            state=MigrationState.adapted,
            superseded_by="PR-003",
            removal_milestone="milestone-C",
            flag="runtime.registry_enabled",
            vnext_only=False,
            legacy_shimmed=False,
            parity_test="tests/runtime/test_compat_wrapper.py",
        ),
        ModuleMigration(
            module="oc_new/conductor.py",
            legacy_symbol="OcNewConductor",
            state=MigrationState.adapted,
            superseded_by="PR-003/004",
            removal_milestone="milestone-C",
            flag="runtime.registry_enabled",
            vnext_only=False,
            legacy_shimmed=False,
            parity_test="tests/runtime/test_convergence_seams.py",
        ),
        # CL-002 legacy workflow surface.
        ModuleMigration(
            module="agents/sdd_orchestrator.py",
            legacy_symbol="WORKFLOW_TRACKS",
            state=MigrationState.adapted,
            superseded_by="PR-003",
            removal_milestone="milestone-C",
            flag="runtime.registry_enabled",
            vnext_only=False,
            legacy_shimmed=False,
            parity_test="tests/workflows/test_resolver_aliases.py",
        ),
        # CL-003 legacy provider/sampling/firewall path (PR-012 pending -> legacy).
        ModuleMigration(
            module="llm/sampling_gateway.py",
            legacy_symbol="SamplingGateway",
            state=MigrationState.legacy,
            superseded_by="PR-012",
            removal_milestone="milestone-E",
            flag="runtime.gateway_enabled",
        ),
        ModuleMigration(
            module="llm/provider_gateway.py",
            legacy_symbol="ProviderGateway",
            state=MigrationState.legacy,
            superseded_by="PR-012",
            removal_milestone="milestone-E",
            flag="runtime.gateway_enabled",
        ),
        ModuleMigration(
            module="safety/firewall.py",
            legacy_symbol="ContextFirewall",
            state=MigrationState.legacy,
            superseded_by="PR-012",
            removal_milestone="milestone-E",
            flag="runtime.gateway_enabled",
        ),
        # CL-004 legacy retrieval planner / packing (PR-010 pending -> legacy).
        ModuleMigration(
            module="retrieval/planner.py",
            legacy_symbol="RetrievalPlanner",
            state=MigrationState.legacy,
            superseded_by="PR-010",
            removal_milestone="milestone-D",
            flag="runtime.context_engine_enabled",
        ),
        ModuleMigration(
            module="context/packing.py",
            legacy_symbol="ContextPackBuilder",
            state=MigrationState.legacy,
            superseded_by="PR-010",
            removal_milestone="milestone-D",
            flag="runtime.context_engine_enabled",
        ),
    ],
)
