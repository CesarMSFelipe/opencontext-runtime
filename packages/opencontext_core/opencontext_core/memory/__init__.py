"""Memory layer exports.

The PR-009 v2 surfaces (``MemoryHarness``, ``MemoryProvider`` /
``MemoryStoreProvider``, the project-files generator, and budgeted retrieval) are
exported lazily via :pep:`562` ``__getattr__`` so importing the ``memory`` package
(which the runtime does eagerly) does not pull the full promotion stack and risk
an import cycle. Access them as ``opencontext_core.memory.MemoryHarness`` etc.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opencontext_core.memory.capture import CaptureEventKind, MemoryCaptureService
from opencontext_core.memory.project_memory import ProjectMemory
from opencontext_core.memory.stores import (
    LocalProjectMemoryStore,
    NullProjectMemoryStore,
    ProjectMemoryStore,
)

if TYPE_CHECKING:
    from opencontext_core.memory.harness import KgLinkPort, MemoryHarness
    from opencontext_core.memory.provider import MemoryProvider, MemoryStoreProvider

__all__ = [
    "CaptureEventKind",
    "KgLinkPort",
    "LocalProjectMemoryStore",
    "MemoryCaptureService",
    "MemoryHarness",
    "MemoryProvider",
    "MemoryStoreProvider",
    "NullProjectMemoryStore",
    "ProjectMemory",
    "ProjectMemoryStore",
    "generate_project_files",
]


def __getattr__(name: str) -> Any:
    if name in ("MemoryHarness", "KgLinkPort"):
        from opencontext_core.memory import harness

        return getattr(harness, name)
    if name in ("MemoryProvider", "MemoryStoreProvider"):
        from opencontext_core.memory import provider

        return getattr(provider, name)
    if name == "generate_project_files":
        from opencontext_core.memory.project_files import generate

        return generate
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
