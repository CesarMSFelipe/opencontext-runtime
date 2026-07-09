"""Shim smoke test for the ``opencontext_core.adapters`` package.

The package-level deprecation facade was removed for 2.0. The adapter classes
are exercised directly under
``packages/opencontext_core/opencontext_core/adapters/*``; this file only
guards that the package still imports and its submodules stay reachable.
"""

from __future__ import annotations


def test_adapters_package_importable_and_submodules_reachable() -> None:
    import opencontext_core.adapters  # noqa: F401
    from opencontext_core.adapters.aider import AiderAdapter
    from opencontext_core.adapters.base import AgentAdapter, AgentResult
    from opencontext_core.adapters.boundary import BoundaryService
    from opencontext_core.adapters.local import LocalAdapter, PythonAdapter

    for cls in (
        AiderAdapter,
        AgentAdapter,
        AgentResult,
        BoundaryService,
        LocalAdapter,
        PythonAdapter,
    ):
        assert isinstance(cls, type)
