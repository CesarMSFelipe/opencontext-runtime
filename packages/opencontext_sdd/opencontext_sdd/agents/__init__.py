"""opencontext_sdd.agents — Adapter interface for host client agents.

Sub-package that ports gentle-ai's 16+ Adapter shape:

* ``interface``: the ``Adapter`` Protocol surface.
* ``factory``: ``build_adapter(name) -> Adapter`` constructor.
* ``registry``: the canonical ``ADAPTERS`` mapping (one entry per host client).

Exposes ``Adapter``, ``ADAPTERS``, ``build_adapter`` and ``UnknownAdapter``
for the SDD orchestrator and tests; sub-modules remain importable for
direct access.
"""

from __future__ import annotations

from opencontext_sdd.agents import factory as _factory
from opencontext_sdd.agents import interface as _interface
from opencontext_sdd.agents import registry as _registry

# Re-export the public surface so callers can ``from opencontext_sdd.agents
# import Adapter, ADAPTERS, build_adapter, UnknownAdapter``.
Adapter = _interface.Adapter
ADAPTERS = _registry.ADAPTERS
build_adapter = _factory.build_adapter
UnknownAdapter = _factory.UnknownAdapter

# Keep the sub-module references on the package namespace so ``opencontext_sdd.
# agents.factory`` resolves for callers reaching for the module directly.
__all__ = [
    "ADAPTERS",
    "Adapter",
    "UnknownAdapter",
    "build_adapter",
    "factory",
    "interface",
    "registry",
]
