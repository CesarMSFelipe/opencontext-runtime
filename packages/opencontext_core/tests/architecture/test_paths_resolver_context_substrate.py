"""Migration pin: context/cache/memory modules route through paths (Phase 1, part 2/3).

The v2 design (commit 004) migrates the context / cache / memory modules
from inline ``.opencontext / .storage / .cache / .runtime`` literal
concatenations to ``paths.resolve_*`` calls. This file pins a representative
set of modules so a regression that re-introduces hardcoded paths fails
the AST scan (Amendment-2) per module.

Per the Phase-1 commit-003 AST gate (``test_paths_resolver_ast``) the count
MUST monotonically decrease as migration commits land; this file asserts
that a representative set of *already-migrated* modules stays clean.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# Import the AST scan helper from the sibling test module. Importing via
# ``importlib`` keeps both test files discoverable without forcing a
# package-name coupling to the conftest.
_AST_TEST = Path(__file__).resolve().parent / "test_paths_resolver_ast.py"
_spec = importlib.util.spec_from_file_location("_paths_resolver_ast", _AST_TEST)
if _spec is None or _spec.loader is None:  # pragma: no cover — defensive
    raise ImportError("cannot locate test_paths_resolver_ast spec")
_ast_mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("_paths_resolver_ast", _ast_mod)
_spec.loader.exec_module(_ast_mod)
scan_hardcoded_paths = _ast_mod.scan_hardcoded_paths


# 15 modules across context/, cache/, memory/. Each one MUST keep zero AST
# hardcoded-path findings. The list mixes already-clean modules with
# explicitly migrated ones (memory/project_files.py is the migration target
# of commit 004).
_MIGRATED_MODULES: tuple[str, ...] = (
    # 5 context modules
    "packages/opencontext_core/opencontext_core/context/engine.py",
    "packages/opencontext_core/opencontext_core/context/receipt.py",
    "packages/opencontext_core/opencontext_core/context/assembler.py",
    "packages/opencontext_core/opencontext_core/context/compiler.py",
    "packages/opencontext_core/opencontext_core/context/broker.py",
    # 5 cache modules
    "packages/opencontext_core/opencontext_core/cache/base.py",
    "packages/opencontext_core/opencontext_core/cache/v2/registry.py",
    "packages/opencontext_core/opencontext_core/cache/v2/base.py",
    "packages/opencontext_core/opencontext_core/cache/v2/semantic.py",
    "packages/opencontext_core/opencontext_core/cache/exact.py",
    # 5 memory modules
    "packages/opencontext_core/opencontext_core/memory/project_files.py",
    "packages/opencontext_core/opencontext_core/memory/stores.py",
    "packages/opencontext_core/opencontext_core/memory/harness.py",
    "packages/opencontext_core/opencontext_core/memory/backends.py",
    "packages/opencontext_core/opencontext_core/memory/benchmark.py",
)


@pytest.mark.parametrize("module_path", _MIGRATED_MODULES)
def test_context_modules_route_through_paths(module_path: str) -> None:
    """Each migrated module must have ZERO AST hardcoded-path findings.

    The AST scanner (Amendment-2) is the source-of-truth gate; the count
    for the whole tree is cap-bound in ``test_paths_resolver_ast``. This
    per-module pin ensures the representative Phase-1 migration set stays
    clean so commit 016's full-tree acceptance gate is reachable.
    """
    findings = [
        (p, ln, snip)
        for (p, ln, snip) in scan_hardcoded_paths()
        if p == module_path
    ]
    assert findings == [], (
        f"hardcoded paths detected in {module_path}: "
        f"{[(ln, snip[:60]) for _, ln, snip in findings]}"
    )
