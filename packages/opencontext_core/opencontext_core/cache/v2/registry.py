"""Cache v2 — `CacheRegistry` (REQ-cache-v2-001).

The seven cache types unified by PR-000.3, in canonical order. The leaf
exposes these as a read-only registry so upper layers (KG, Memory,
Context, Provider) can introspect what the leaf accepts without
importing any of them.
"""

from __future__ import annotations

from typing import Final

from opencontext_core.cache.base import CacheType

_CACHE_TYPES: Final[tuple[str, ...]] = (
    CacheType.semantic.value,
    CacheType.prompt_context.value,
    CacheType.tool_output.value,
    CacheType.ast.value,
    CacheType.provider_response.value,
    CacheType.kg_query.value,
    CacheType.memory_retrieval.value,
)


class CacheRegistry:
    """Read-only registry of the seven cache types (doc 59 — book §5)."""

    @staticmethod
    def list() -> list[str]:
        return list(_CACHE_TYPES)

    @staticmethod
    def count() -> int:
        return len(_CACHE_TYPES)

    @staticmethod
    def contains(name: str) -> bool:
        return name in _CACHE_TYPES


__all__ = ["CacheRegistry"]
