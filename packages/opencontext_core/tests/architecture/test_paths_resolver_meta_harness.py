"""Migration pin: harness/runtime/sdk modules route through paths (Phase 1, part 3/3).

The v2 design (commit 005) migrates the harness / runtime / sdk modules
from inline ``.opencontext / .storage / .cache / .runtime`` literal
concatenations to ``paths.resolve_*`` calls. This file pins a
representative set of modules so a regression that re-introduces
hardcoded paths fails the AST scan (Amendment-2) per module.

Companion to commit 004's
``test_paths_resolver_context_substrate.py``. Together they partition the
~30 v1 hardcoded-path modules into context/cache/memory and
harness/runtime/sdk groups; both pins enforce the per-module zero
finding guarantee.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Import the AST scan helper from the sibling test module via spec
# loading so the conftest does not need to widen pythonpath.
_AST_TEST = Path(__file__).resolve().parent / "test_paths_resolver_ast.py"
_spec = importlib.util.spec_from_file_location("_paths_resolver_ast", _AST_TEST)
if _spec is None or _spec.loader is None:  # pragma: no cover — defensive
    raise ImportError("cannot locate test_paths_resolver_ast spec")
_ast_mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("_paths_resolver_ast", _ast_mod)
_spec.loader.exec_module(_ast_mod)
scan_hardcoded_paths = _ast_mod.scan_hardcoded_paths


# 15 modules across harness/, runtime/, sdk/. Each one MUST keep zero AST
# hardcoded-path findings. Migrated in commit 005:
# - harness/checkpoint.py (root constructor)
# - harness/run_store.py (runs_path constructor)
# - harness/sessions.py (sessions_root helper)
# - runtime/session_store.py (sessions_path constructor)
_MIGRATED_MODULES: tuple[str, ...] = (
    # 5 harness modules
    "packages/opencontext_core/opencontext_core/harness/checkpoint.py",
    "packages/opencontext_core/opencontext_core/harness/run_store.py",
    "packages/opencontext_core/opencontext_core/harness/sessions.py",
    "packages/opencontext_core/opencontext_core/harness/artifact_store.py",
    "packages/opencontext_core/opencontext_core/harness/receipt_store.py",
    # 5 runtime modules
    "packages/opencontext_core/opencontext_core/runtime/session_store.py",
    "packages/opencontext_core/opencontext_core/runtime/api.py",
    "packages/opencontext_core/opencontext_core/runtime/brain.py",
    "packages/opencontext_core/opencontext_core/runtime/scheduler.py",
    "packages/opencontext_core/opencontext_core/runtime/run.py",
    # 5 sdk modules
    "packages/opencontext_core/opencontext_core/sdk/__init__.py",
    "packages/opencontext_core/opencontext_core/sdk/platform.py",
    "packages/opencontext_core/opencontext_core/sdk/auth.py",
    "packages/opencontext_core/opencontext_core/sdk/router.py",
    "packages/opencontext_core/opencontext_core/sdk/observability.py",
)


@pytest.mark.parametrize("module_path", _MIGRATED_MODULES)
def test_harness_runtime_sdk_route_through_paths(module_path: str) -> None:
    """Each migrated module must have ZERO AST hardcoded-path findings.

    Companion to commit 004's context/cache/memory pin. Together these
    tests enforce that the Phase-1 migration set stays clean so commit
    016's full-tree acceptance gate is reachable.
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
