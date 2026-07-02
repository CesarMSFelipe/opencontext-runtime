"""Architecture gate: divergent KG-path consumers must not pin StorageMode.local.

C1 (product-closure-r13): The 4 consumers identified in the explore phase
(verification.py, harness/meta.py, agentic/context_substrate.py,
harness/gates.py) must resolve KG/storage paths via the config-driven helper
(resolve_active_storage_path / resolve_active_workspace_path) instead of
pinning StorageMode.local directly.

This test fails until all 4 consumers are migrated (C1 commit).

Allowlist rationale:
  - paths/ (the definition of StorageMode)
  - config_resolver.py (_global_config_path legitimately uses StorageMode.local
    for the HOME user config, not project storage)
  - runtime/__init__.py line 341 (explicit backward-compat storage_path override)
  - config.py (StorageMode type definition)
  - _effective_mode (the canonical mode-override function)

Files under test (must NOT use StorageMode.local for KG/project-storage paths):
  - verification.py — check_knowledge_graph must use the active resolver
  - harness/meta.py — _check_kg_snapshot_path must use the active resolver
  - agentic/context_substrate.py — build_for_phase must use the active resolver
  - harness/gates.py — ProjectIndexExistsGate must use the active resolver
"""

from __future__ import annotations

import ast
from pathlib import Path

# Productive source root (packages/opencontext_core/opencontext_core/)
# parents[0]=tests/architecture, parents[1]=tests, parents[2]=repo root
_PROD_ROOT = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "opencontext_core"
    / "opencontext_core"
)

# Files that must NOT pin StorageMode.local for KG/storage-path resolution.
_DIVERGENT_CONSUMERS = [
    _PROD_ROOT / "harness" / "meta.py",
    _PROD_ROOT / "agentic" / "context_substrate.py",
    _PROD_ROOT / "harness" / "gates.py",
]


def _find_pinned_storage_mode_local(source_path: Path) -> list[int]:
    """Return line numbers where StorageMode.local appears as a direct attribute access.

    Matches AST patterns of the form:
        StorageMode.local   (ast.Attribute with .attr=="local" where .value is
                             ast.Name(id="StorageMode") or ast.Attribute(attr="StorageMode"))

    Does NOT match:
        - String literals "local"
        - The _effective_mode function body (legitimate comparison, inside paths/)
    """
    try:
        source = source_path.read_text(encoding="utf-8")
    except OSError:
        return []

    try:
        tree = ast.parse(source, filename=str(source_path))
    except SyntaxError:
        return []

    lines: list[int] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Attribute) and node.attr == "local"):
            continue
        # Match: StorageMode.local where StorageMode is a Name or an attribute chain
        val = node.value
        if isinstance(val, ast.Name) and val.id == "StorageMode":
            lines.append(node.lineno)
        elif isinstance(val, ast.Attribute) and val.attr == "StorageMode":
            lines.append(node.lineno)
    return lines


def test_no_pinned_storage_mode() -> None:
    """The 4 divergent KG-path consumers must not pin StorageMode.local.

    Strict TDD: this test FAILS until C1 migrates each consumer to
    resolve_active_storage_path / resolve_active_workspace_path.
    """
    violations: list[str] = []
    for path in _DIVERGENT_CONSUMERS:
        assert path.exists(), f"Consumer file not found: {path}"
        bad_lines = _find_pinned_storage_mode_local(path)
        for lineno in bad_lines:
            violations.append(f"{path.relative_to(_PROD_ROOT.parent.parent)}:{lineno}")

    assert not violations, (
        "Divergent consumers still pin StorageMode.local — "
        "migrate to resolve_active_storage_path / resolve_active_workspace_path:\n"
        + "\n".join(f"  {v}" for v in violations)
    )
