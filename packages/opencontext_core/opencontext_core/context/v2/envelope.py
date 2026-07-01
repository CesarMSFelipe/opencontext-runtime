"""Context v2 envelope (canonical prompt carrier) + lazy re-exports.

Back-compat: ``from opencontext_core.context.v2.envelope import
ContextRanker`` still works — the heavy classes live in their own
modules; envelope re-exports them on first access to break the
ranking/routing/compression → envelope → … cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextEnvelope:
    task: str
    items: list[dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0
    budget: int = 3000
    omissions: list[str] = field(default_factory=list)
    compressed: bool = False


_LAZY = {
    "ContextRanker": "opencontext_core.context.v2.ranking",
    "ContextRouter": "opencontext_core.context.v2.routing",
    "ContextCompressor": "opencontext_core.context.v2.compression",
    "usefulness_score": "opencontext_core.context.v2.usefulness",
}


def __getattr__(name: str):  # PEP 562 lazy re-export
    mod_name = _LAZY.get(name)
    if mod_name is None:
        raise AttributeError(name)
    import importlib
    module = importlib.import_module(mod_name)
    value = getattr(module, name)
    globals()[name] = value  # cache
    return value


__all__ = [
    "ContextCompressor",
    "ContextEnvelope",
    "ContextRanker",
    "ContextRouter",
    "usefulness_score",
]