"""Agent adapters for AI coding tool integration and boundary dispatch.

.. deprecated:: 1.5.0
    The adapter layer (``AgentAdapter``, ``AiderAdapter``, ``LocalAdapter``,
    ``PythonAdapter``, ``BoundaryService``) is deprecated and will be removed in
    2.0. The harness drives agents through the sampling gateway instead.
    Package-level access (``from opencontext_core.adapters import X``) emits a
    ``DeprecationWarning``; direct submodule imports are left untouched so internal
    health checks do not trip the warning.
"""

from __future__ import annotations

import importlib
import warnings
from typing import Any

# Public name -> (submodule, attribute). Names resolve lazily via __getattr__
# (returning Any) so deprecated SDK imports keep working with a warning.
_DEPRECATED: dict[str, tuple[str, str]] = {
    "AdapterRequest": ("boundary", "AdapterRequest"),
    "AdapterTarget": ("boundary", "AdapterTarget"),
    "AgentAdapter": ("base", "AgentAdapter"),
    "AgentResult": ("base", "AgentResult"),
    "AiderAdapter": ("aider", "AiderAdapter"),
    "BoundaryResult": ("boundary", "BoundaryResult"),
    "BoundaryService": ("boundary", "BoundaryService"),
    "LocalAdapter": ("local", "LocalAdapter"),
    "PythonAdapter": ("local", "PythonAdapter"),
}

__all__ = list(_DEPRECATED)


def __getattr__(name: str) -> Any:
    """Lazily resolve a public adapter name, warning that the layer is deprecated.

    Submodule imports (e.g. ``from opencontext_core.adapters.aider import
    AiderAdapter``) bypass this hook, so internal health checks that import
    submodules directly do not trip the warning — only package-level SDK access.
    """
    target = _DEPRECATED.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    warnings.warn(
        "opencontext_core.adapters is deprecated and will be removed in 2.0.",
        DeprecationWarning,
        stacklevel=2,
    )
    module = importlib.import_module(f"opencontext_core.adapters.{target[0]}")
    return getattr(module, target[1])
