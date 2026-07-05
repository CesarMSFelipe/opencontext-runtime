"""Architecture coverage — AST guard + traceability matrix.

The coverage walker is the contract between the v2 module set and the
release-gate machinery. It does two things:

1. **AST guard.** Walk ``packages/opencontext_core/opencontext_core/``
    for every v2 subpackage and assert the module's top-level
    ``__capability__`` annotation is present and a string. This is the
    ratchet that prevents new v2 modules from sneaking in without a
    stable capability id.

2. **Traceability matrix.** Build a row per registered v2 capability
    with the module path, the test directory that covers it, and the
    SPEC / PR reference. The matrix is the audit artifact reviewers
    can scan.

Both the walker and the matrix are pure-data; no runtime side effects,
no filesystem writes outside the report. The CLI entry point
``opencontext architecture coverage`` lives in the opencontext_cli
package; this module is the library surface.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, TypedDict


class TraceabilityRow(TypedDict):
    """One row in the architecture coverage traceability matrix."""

    id: str
    module: str
    tests: str
    spec: str


class TraceabilityMatrix(TypedDict):
    """Full traceability matrix returned by :func:`build_traceability_matrix`."""

    schema_version: str
    rows: list[TraceabilityRow]


TRACEABILITY_SCHEMA_VERSION = "opencontext.architecture_coverage.v1"

# Spec/PR references for the eight v2 capabilities. These are static;
# the v2 module is the source of truth for the id itself.
_SPEC_BY_CAPABILITY: dict[str, str] = {
    "graph.v2": "PR-008 / SPEC §3.2 graph",
    "context.v2": "PR-011 / SPEC §3.2 context",
    "memory.v2": "PR-014 / SPEC §3.2 memory",
    "learning.v2": "PR-018 / SPEC §3.2 learning",
    "cache.v2": "PR-016 / SPEC §3.2 cache",
    "plugins.v2": "PR-015 / SPEC §3.2 plugins",
    "marketplace.v2": "PR-017 / SPEC §3.2 marketplace",
    "providers.v2": "PR-012 / SPEC §3.2 providers",
}

# Test directory for each v2 capability. The directory may not exist for
# every v2 subpackage; the matrix records the expected path.
_TESTS_BY_CAPABILITY: dict[str, str] = {
    "graph.v2": "packages/opencontext_core/tests/graph/v2/",
    "context.v2": "packages/opencontext_core/tests/context/v2/",
    "memory.v2": "packages/opencontext_core/tests/memory/v2/",
    "learning.v2": "packages/opencontext_core/tests/learning/v2/",
    "cache.v2": "packages/opencontext_core/tests/cache/v2/",
    "plugins.v2": "packages/opencontext_core/tests/plugins/v2/",
    "marketplace.v2": "packages/opencontext_core/tests/marketplace/v2/",
    "providers.v2": "packages/opencontext_core/tests/providers/v2/",
}


def _capability_id_for_v2_dir(dirname: str) -> str:
    """Translate a v2 subpackage directory name into a stable capability id.

    The mapping is ``<dirname>.v2`` — e.g. ``graph`` -> ``graph.v2``.
    The ``dirname`` is the parent of the v2 directory, not the v2
    directory itself.
    """
    return f"{dirname}.v2"


def registered_capability_ids() -> frozenset[str]:
    """Return the set of v2 capability ids registered with the capability registry.

    Re-exports from :mod:`opencontext_core.capabilities.registry` so the
    coverage report and the registry cannot drift.
    """
    # Imported lazily to avoid an import cycle at module-load time.
    from opencontext_core.capabilities.registry import REGISTERED_V2_CAPABILITIES

    return REGISTERED_V2_CAPABILITIES


def walk_v2_modules(core_root: Path) -> list[Path]:
    """Return every v2 subpackage directory directly under ``core_root``.

    A v2 subpackage is a directory named ``v2`` whose parent is a
    top-level package directory under ``core_root`` (e.g. ``graph/v2``,
    ``context/v2``). The returned paths point at the ``v2`` directory
    itself; the caller inspects its ``__init__.py`` for the
    ``__capability__`` annotation.

    The eight v2 capabilities registered with the capability registry
    are the ones the coverage walker tracks. Other v2 subpackages that
    exist in the tree (e.g. ``benchmarks/v2``) are tracked separately
    by their own gate machinery and are excluded here.
    """
    if not core_root.exists():
        return []
    registered = registered_capability_ids()
    found: list[Path] = []
    for child in sorted(core_root.iterdir()):
        if not child.is_dir():
            continue
        candidate = child / "v2"
        cap_id = _capability_id_for_v2_dir(child.name)
        if candidate.is_dir() and (candidate / "__init__.py").exists() and cap_id in registered:
            found.append(candidate)
    return found


def _capability_id_for_init(init_path: Path) -> str:
    """Return the expected capability id for a v2 ``__init__.py`` file.

    The id is derived from the parent of the v2 directory (i.e. the
    grandparent of the init file): ``<dirname>.v2``.
    """
    return _capability_id_for_v2_dir(init_path.parent.parent.name)


def iter_v2_modules(core_root: Path) -> list[Path]:
    """Return every v2 module file (``__init__.py``) the walker tracks.

    The architecture guard's contract is: every v2 subpackage in the
    closed set of registered capabilities has a ``__init__.py`` carrying
    the ``__capability__`` annotation. The subpackage's ``__init__`` is
    the single source of the id; sibling modules are not enforced.
    """
    inits: list[Path] = []
    for v2_dir in walk_v2_modules(core_root):
        init = v2_dir / "__init__.py"
        if init.exists():
            inits.append(init)
    return inits


def _read_capability_id(init_path: Path) -> str | None:
    """Read the ``__capability__`` string annotation from a v2 ``__init__.py``.

    Returns ``None`` when the annotation is missing or not a string. The
    AST walk is intentionally minimal — only the first top-level
    assignment to ``__capability__`` is consulted.
    """
    source = init_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "__capability__"
        ):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
    return None


def build_traceability_matrix(core_root: Path) -> TraceabilityMatrix:
    """Build the v2 traceability matrix.

    One row per discovered v2 subpackage. The matrix is the audit
    artifact emitted by ``opencontext architecture coverage`` and stored
    next to release evidence.
    """
    rows: list[TraceabilityRow] = []
    for v2_dir in walk_v2_modules(core_root):
        init = v2_dir / "__init__.py"
        cap_id = _read_capability_id(init) or _capability_id_for_init(init)
        module_relpath = v2_dir.relative_to(core_root.parent).as_posix()
        rows.append(
            TraceabilityRow(
                id=cap_id,
                module=module_relpath,
                tests=_TESTS_BY_CAPABILITY.get(cap_id, ""),
                spec=_SPEC_BY_CAPABILITY.get(cap_id, ""),
            )
        )
    rows.sort(key=lambda r: r["id"])
    return TraceabilityMatrix(
        schema_version=TRACEABILITY_SCHEMA_VERSION,
        rows=rows,
    )


def _missing_annotation_modules(core_root: Path) -> list[str]:
    """Return v2 modules whose ``__init__.py`` lacks ``__capability__``."""
    missing: list[str] = []
    for init in iter_v2_modules(core_root):
        if _read_capability_id(init) is None:
            missing.append(init.relative_to(core_root.parent).as_posix())
    return missing


def coverage_report(core_root: Path) -> dict[str, Any]:
    """Render the full coverage report — used by the CLI command.

    Combines the discovered v2 modules, the registered ids, the
    traceability matrix, and the missing-annotation list. Always
    returns a dict; never raises.
    """
    discovered = sorted(_capability_id_for_init(p) for p in iter_v2_modules(core_root))
    registered = sorted(registered_capability_ids())
    matrix = build_traceability_matrix(core_root)
    return {
        "schema_version": TRACEABILITY_SCHEMA_VERSION,
        "discovered": discovered,
        "registered": registered,
        "missing_annotation": _missing_annotation_modules(core_root),
        "matrix": matrix,
    }
