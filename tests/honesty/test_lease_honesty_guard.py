"""Honesty guard: no product source advertises lease/AgentCoordination as active.

REQ-B10: No product source file shall present lease management or
AgentCoordinationStore as an active runtime capability. This guard test
asserts zero matches for active-capability claim strings in non-test source
under packages/opencontext_cli and packages/opencontext_core.
"""

from __future__ import annotations

from pathlib import Path

# Strings that would indicate an active-capability claim for lease/coordination.
_FORBIDDEN_PATTERNS = [
    "coordination active",
    "leases enabled",
    "active lease",
]

_PACKAGES_ROOT = Path(__file__).parents[2] / "packages"

# Excluded from the guard: these files *are* the lease implementation; references
# to "active lease" there are internal runtime checks, not user-facing capability ads.
_EXCLUDED_FILES = {
    "leases.py",
}


def _non_test_python_sources() -> list[Path]:
    """Collect non-test .py files under opencontext_cli and opencontext_core."""
    sources: list[Path] = []
    for pkg in ("opencontext_cli", "opencontext_core"):
        pkg_dir = _PACKAGES_ROOT / f"opencontext_{pkg.split('_', 1)[-1]}" / pkg
        if not pkg_dir.exists():
            # Try the direct package name as folder name matches pkg var
            pkg_dir = _PACKAGES_ROOT / pkg / pkg
        for py_file in pkg_dir.rglob("*.py"):
            # Exclude test files, __pycache__, and the lease implementation itself.
            rel = py_file.relative_to(_PACKAGES_ROOT)
            parts = rel.parts
            if any(p in ("__pycache__", "tests", "test") or p.startswith("test_") for p in parts):
                continue
            if py_file.name.startswith("test_"):
                continue
            if py_file.name in _EXCLUDED_FILES:
                continue
            sources.append(py_file)
    return sources


def test_no_active_lease_claim_in_product_source() -> None:
    """Assert no product source contains active-capability claim strings for leases."""
    sources = _non_test_python_sources()
    assert sources, "No source files found — check package paths in test"

    violations: list[str] = []
    for src in sources:
        try:
            text = src.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern.lower() in text:
                violations.append(f"{src}: contains {pattern!r}")

    assert not violations, (
        "Active lease/coordination capability claims found in product source "
        "(REQ-B10 violation):\n" + "\n".join(violations)
    )
