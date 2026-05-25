"""Agent adapters for AI coding tool integration and boundary dispatch."""

from opencontext_core.adapters.aider import AiderAdapter
from opencontext_core.adapters.base import AgentAdapter, AgentResult
from opencontext_core.adapters.boundary import (
    AdapterRequest,
    AdapterTarget,
    BoundaryResult,
    BoundaryService,
)
from opencontext_core.adapters.local import LocalAdapter, PythonAdapter

__all__ = [
    "AdapterRequest",
    "AdapterTarget",
    "AgentAdapter",
    "AgentResult",
    "AiderAdapter",
    "BoundaryResult",
    "BoundaryService",
    "LocalAdapter",
    "PythonAdapter",
]
