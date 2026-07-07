"""Formal executor registry + built-in executors (plan doc 2 §14, EXE tests).

``registry`` declares every executor the runtime can attach with honest
capability flags; ``patch`` is the unified-diff-driven executor (EXE-004).
"""

from opencontext_core.executors.registry import (
    ExecutorRegistry,
    ExecutorSpec,
    default_registry,
)

__all__ = ["ExecutorRegistry", "ExecutorSpec", "default_registry"]
