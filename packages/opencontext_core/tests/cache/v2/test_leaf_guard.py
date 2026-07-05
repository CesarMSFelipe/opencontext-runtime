"""REQ-cache-v2-002 — leaf_guard ast walk: zero upward imports."""

from __future__ import annotations


class TestLeafGuard:
    def test_no_upward_imports_in_cache_v2(self) -> None:
        """All modules under cache/v2/ must avoid upward imports."""
        from opencontext_core.cache.v2.leaf_guard import verify_no_upward_imports

        violations = verify_no_upward_imports()
        assert violations == [], f"upward imports detected: {violations}"

    def test_upward_import_detected_on_violator(self) -> None:
        """Sentinel module that imports a forbidden namespace must fail the check."""
        import textwrap
        from pathlib import Path

        from opencontext_core.cache.v2.leaf_guard import (
            FORBIDDEN_UPWARD_NAMESPACES,
            scan_module_for_upward_imports,
        )

        fake_src = textwrap.dedent(
            """
            from opencontext_core.context.engine import SomeThing  # forbidden
            """
        ).strip()
        violators = scan_module_for_upward_imports(
            module_path=Path("cache/v2/__synthetic_violator__.py"),
            source=fake_src,
            forbidden=FORBIDDEN_UPWARD_NAMESPACES,
        )
        assert len(violators) == 1
        assert violators[0].target.startswith("opencontext_core.context")
        assert violators[0].source == "cache/v2/__synthetic_violator__.py"
