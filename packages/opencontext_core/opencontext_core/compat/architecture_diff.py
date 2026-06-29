"""PROD-005 / B5 — architecture governance diff (contracts + dependency edges).

A thin presenter over the same AST snapshot the ``test_no_contract_drift`` fitness
guard computes. It snapshots every ``VersionedContract`` subclass (schema_version +
declared fields) and the eager cross-package dependency edges, then diffs the live
state against a frozen, source-controlled baseline
(``tests/architecture/architecture-baseline.json``):

* a contract added / removed, or whose field-set or ``schema_version`` changed →
  reported as a contract drift item;
* a cross-package import edge added / removed → reported as a dependency drift item.

Contract comparison reuses :func:`opencontext_core.compat.parity.check_parity` (the
shipped parity primitive) rather than a bespoke comparator. The baseline JSON carries
both a ``contracts`` map (the externalized drift-guard baseline) and a
``dependency_edges`` list, so the same artifact backs the drift guard AND the
``opencontext architecture diff`` command.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict

from .parity import check_parity

#: Root of the ``opencontext_core`` package this module lives in. ``architecture_diff``
#: sits at ``opencontext_core/compat/architecture_diff.py`` → ``parents[1]`` is the
#: package directory whose tree is snapshotted.
PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class ArchitectureSnapshot(BaseModel):
    """A point-in-time architecture snapshot: versioned contracts + dependency edges."""

    model_config = ConfigDict(extra="forbid")

    #: ``"relpath:ClassName"`` → ``{"schema_version": str|None, "fields": [str, ...]}``.
    contracts: dict[str, dict[str, object]]
    #: Sorted ``"src_pkg->dst_pkg"`` eager cross-package import edges.
    dependency_edges: list[str]


class ArchitectureDiff(BaseModel):
    """Structured diff of a live snapshot against the architecture baseline."""

    model_config = ConfigDict(extra="forbid")

    added_contracts: list[str]
    removed_contracts: list[str]
    changed_contracts: list[str]
    added_dependencies: list[str]
    removed_dependencies: list[str]

    @property
    def has_drift(self) -> bool:
        """True when any contract or dependency drift was detected."""
        return bool(
            self.added_contracts
            or self.removed_contracts
            or self.changed_contracts
            or self.added_dependencies
            or self.removed_dependencies
        )


def _base_names(cd: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for base in cd.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
    return names


def snapshot_contracts() -> dict[str, dict[str, object]]:
    """AST-snapshot every VersionedContract subclass: schema_version + declared fields."""
    snap: dict[str, dict[str, object]] = {}
    for py in PACKAGE_ROOT.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = py.relative_to(PACKAGE_ROOT).as_posix()  # posix keys: stable across OSes
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or "VersionedContract" not in _base_names(node):
                continue
            fields: list[str] = []
            schema_version: str | None = None
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    name = stmt.target.id
                    if name == "schema_version":
                        if isinstance(stmt.value, ast.Constant):
                            schema_version = str(stmt.value.value)
                    else:
                        fields.append(name)
            snap[f"{rel}:{node.name}"] = {
                "schema_version": schema_version,
                "fields": sorted(fields),
            }
    return snap


def _eager_imported_packages(node: ast.AST) -> list[str]:
    out: list[str] = []
    if isinstance(node, ast.ImportFrom):
        mod = node.module or ""
        if mod.startswith("opencontext_core.") and node.level == 0:
            out.append(mod.split(".")[1])
    elif isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.startswith("opencontext_core."):
                out.append(alias.name.split(".")[1])
    return out


def snapshot_dependency_edges() -> list[str]:
    """Sorted ``"src->dst"`` eager (module-top) cross-package import edges.

    Mirrors the eager-only policy of the layering guard: only top-of-module imports
    are recorded (those are the edges that create import-time coupling). Self-edges
    and non-package single-module files are ignored.
    """
    edges: set[str] = set()
    for py in PACKAGE_ROOT.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        rel = py.relative_to(PACKAGE_ROOT)
        src = rel.parts[0] if len(rel.parts) > 1 else rel.stem
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for stmt in tree.body:
            if not isinstance(stmt, (ast.Import, ast.ImportFrom)):
                continue
            for dst in _eager_imported_packages(stmt):
                if dst != src:
                    edges.add(f"{src}->{dst}")
    return sorted(edges)


def current_snapshot() -> ArchitectureSnapshot:
    """Snapshot the live contracts and dependency edges of the package."""
    return ArchitectureSnapshot(
        contracts=snapshot_contracts(),
        dependency_edges=snapshot_dependency_edges(),
    )


def load_baseline(path: Path) -> ArchitectureSnapshot:
    """Load the frozen architecture baseline from *path* (``architecture-baseline.json``)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    contracts = data.get("contracts", {})
    edges = data.get("dependency_edges", [])
    return ArchitectureSnapshot(contracts=contracts, dependency_edges=edges)


def _contract_change(name: str, base: dict[str, object], cur: dict[str, object]) -> str | None:
    """Concise drift message for one shared contract, or None when unchanged.

    Equivalence is gated through the shipped ``check_parity`` primitive; when it
    fails, a field/version delta is computed for the human-readable message.
    """
    report = check_parity(
        subsystem=name,
        flag=str(base.get("schema_version")),
        legacy=base,
        vnext=cur,
    )
    if report.passed:
        return None
    base_fields = set(cast("list[str]", base.get("fields", [])))
    cur_fields = set(cast("list[str]", cur.get("fields", [])))
    parts: list[str] = []
    if base.get("schema_version") != cur.get("schema_version"):
        parts.append(
            f"schema_version {base.get('schema_version')!r} -> {cur.get('schema_version')!r}"
        )
    added = sorted(cur_fields - base_fields)
    removed = sorted(base_fields - cur_fields)
    if added:
        parts.append(f"added fields {added}")
    if removed:
        parts.append(f"removed fields {removed}")
    return f"{name}: " + "; ".join(parts)


def diff(baseline: ArchitectureSnapshot, current: ArchitectureSnapshot) -> ArchitectureDiff:
    """Diff *current* against *baseline*: contract + dependency-edge drift."""
    base_c, cur_c = baseline.contracts, current.contracts
    added_contracts = sorted(name for name in cur_c if name not in base_c)
    removed_contracts = sorted(name for name in base_c if name not in cur_c)
    changed_contracts = sorted(
        msg
        for name in base_c
        if name in cur_c
        for msg in (_contract_change(name, base_c[name], cur_c[name]),)
        if msg is not None
    )

    base_e, cur_e = set(baseline.dependency_edges), set(current.dependency_edges)
    added_dependencies = sorted(cur_e - base_e)
    removed_dependencies = sorted(base_e - cur_e)

    return ArchitectureDiff(
        added_contracts=added_contracts,
        removed_contracts=removed_contracts,
        changed_contracts=changed_contracts,
        added_dependencies=added_dependencies,
        removed_dependencies=removed_dependencies,
    )


def run_architecture_diff(baseline_path: Path) -> ArchitectureDiff:
    """Convenience: diff the live snapshot against the baseline at *baseline_path*."""
    return diff(load_baseline(baseline_path), current_snapshot())


__all__ = [
    "ArchitectureDiff",
    "ArchitectureSnapshot",
    "current_snapshot",
    "diff",
    "load_baseline",
    "run_architecture_diff",
    "snapshot_contracts",
    "snapshot_dependency_edges",
]
