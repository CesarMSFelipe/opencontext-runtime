"""Coverage walker + traceability matrix — release-gate architecture surface.

Tests in this file pin the contract for the v2 capability coverage gate:

1. Exactly eight v2 capabilities are registered in
   :mod:`opencontext_core.capabilities.registry` and that set is
   closed/known — no extra ids leak in.
2. The eight v2 subpackages under ``opencontext_core/<x>/v2/`` all exist
   and each one carries a string ``__capability__`` annotation in its
   ``__init__.py``.
3. The traceability matrix produced by
   :func:`opencontext_core.architecture.coverage.build_traceability_matrix`
   is non-empty and has one row per registered capability.
4. The coverage report surfaces the missing-annotation list (empty for
   a healthy tree).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.architecture.coverage import (
    TRACEABILITY_SCHEMA_VERSION,
    build_traceability_matrix,
    coverage_report,
    iter_v2_modules,
    registered_capability_ids,
    walk_v2_modules,
)
from opencontext_core.capabilities.registry import REGISTERED_V2_CAPABILITIES

CORE_ROOT = Path("packages/opencontext_core/opencontext_core")

# The closed set of v2 capability ids this release covers. Adding a new
# v2 module is intentional work — change both this set and the registry
# in the same commit, with a SPEC/PR reference.
EXPECTED_V2_CAPABILITY_IDS: frozenset[str] = frozenset(
    {
        "graph.v2",
        "context.v2",
        "memory.v2",
        "learning.v2",
        "cache.v2",
        "plugins.v2",
        "marketplace.v2",
        "providers.v2",
    }
)


def test_eight_capabilities_registered() -> None:
    """The registry exposes exactly the eight expected v2 capability ids."""
    assert REGISTERED_V2_CAPABILITIES == EXPECTED_V2_CAPABILITY_IDS
    assert len(REGISTERED_V2_CAPABILITIES) == 8
    # And the helper re-export agrees with the registry.
    assert registered_capability_ids() == EXPECTED_V2_CAPABILITY_IDS


def test_walk_v2_modules_returns_eight_subpackages() -> None:
    """The walker discovers exactly the eight v2 subpackages under the core root."""
    found = walk_v2_modules(CORE_ROOT)
    found_ids = {p.parent.name + ".v2" for p in found}
    assert found_ids == EXPECTED_V2_CAPABILITY_IDS
    assert len(found) == 8


def test_iter_v2_modules_returns_init_files() -> None:
    """``iter_v2_modules`` returns the eight ``__init__.py`` files."""
    inits = iter_v2_modules(CORE_ROOT)
    assert len(inits) == 8
    for init in inits:
        assert init.name == "__init__.py"
        assert init.parent.name == "v2"


def test_every_v2_module_has_capability_annotation() -> None:
    """Every discovered v2 ``__init__.py`` carries a string ``__capability__``."""
    missing: list[str] = []
    for init in iter_v2_modules(CORE_ROOT):
        text = init.read_text(encoding="utf-8")
        if "__capability__" not in text:
            missing.append(str(init))
    assert missing == [], f"v2 modules missing __capability__ annotation: {missing}"


def test_capability_annotations_match_registered_ids() -> None:
    """The ``__capability__`` string in each v2 ``__init__.py`` matches its dir-derived id."""
    import ast

    for init in iter_v2_modules(CORE_ROOT):
        tree = ast.parse(init.read_text(encoding="utf-8"))
        assigned: list[str] = []
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "__capability__"
            ):
                value = node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    assigned.append(value.value)
        expected_id = init.parent.parent.name + ".v2"
        assert expected_id in assigned, (
            f"{init} has __capability__={assigned!r}, expected {expected_id!r}"
        )


def test_traceability_matrix_complete() -> None:
    """The traceability matrix has a row for every registered capability."""
    matrix = build_traceability_matrix(CORE_ROOT)
    assert matrix["schema_version"] == TRACEABILITY_SCHEMA_VERSION
    row_ids = {row["id"] for row in matrix["rows"]}
    assert row_ids == EXPECTED_V2_CAPABILITY_IDS
    # Every row references a non-empty module path that ends in /v2.
    for row in matrix["rows"]:
        assert row["module"].endswith("/v2")
        assert row["module"] != ""


def test_coverage_report_has_no_missing_annotations() -> None:
    """The coverage report's missing-annotation list is empty for the healthy tree."""
    report = coverage_report(CORE_ROOT)
    assert report["schema_version"] == TRACEABILITY_SCHEMA_VERSION
    assert set(report["discovered"]) == EXPECTED_V2_CAPABILITY_IDS
    assert set(report["registered"]) == EXPECTED_V2_CAPABILITY_IDS
    assert report["missing_annotation"] == []
    assert report["matrix"]["schema_version"] == TRACEABILITY_SCHEMA_VERSION


def test_walk_v2_modules_handles_missing_root() -> None:
    """Walker returns an empty list when the root does not exist (no crash)."""
    bogus = Path("/nonexistent/path/that/should/never/exist/abc123")
    assert walk_v2_modules(bogus) == []
    assert iter_v2_modules(bogus) == []


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
