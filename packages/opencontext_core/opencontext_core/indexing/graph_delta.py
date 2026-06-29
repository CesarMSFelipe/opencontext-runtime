"""Typed incremental-index delta and cache-invalidation hooks (PR-008, KG-08/CONV.3).

``GraphDelta`` (OC-KG-001 §13) is the typed result of an incremental reindex: the
ids added/updated/deleted plus the symbols/files affected. It is additive over the
existing ``KnowledgeGraph.reindex_files`` dict path — the legacy stats return is
untouched; the typed delta is produced by ``KnowledgeGraph.reindex_delta``.

Cache-invalidation hooks (KG-CONV) let dependent semantic / KG-query / retrieval
caches drop stale entries when the graph mutates, WITHOUT this module importing the
Cache subsystem (doc 58: Cache is an L4 leaf called by KG, never imported by it).
Consumers register a plain callable; the KG fires it with the affected keys.

Layering (doc 58): L4 (KG substrate). Imports only L0 ``pydantic``/stdlib.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field


class GraphDelta(BaseModel):
    """The set of changes produced by an incremental index pass (OC-KG-001 §13)."""

    model_config = ConfigDict(extra="forbid")

    added_nodes: list[str] = Field(default_factory=list, description="Ids of newly added nodes.")
    updated_nodes: list[str] = Field(default_factory=list, description="Ids of updated nodes.")
    deleted_nodes: list[str] = Field(default_factory=list, description="Ids of removed nodes.")
    added_edges: list[str] = Field(default_factory=list, description="Ids of newly added edges.")
    updated_edges: list[str] = Field(default_factory=list, description="Ids of updated edges.")
    deleted_edges: list[str] = Field(default_factory=list, description="Ids of removed edges.")
    affected_symbols: list[str] = Field(
        default_factory=list, description="Symbol/node ids touched by the change."
    )
    affected_files: list[str] = Field(
        default_factory=list, description="Project-relative files touched by the change."
    )

    def is_empty(self) -> bool:
        """True when no node or edge changed (nothing to invalidate)."""
        return not (
            self.added_nodes
            or self.updated_nodes
            or self.deleted_nodes
            or self.added_edges
            or self.updated_edges
            or self.deleted_edges
        )

    def cache_keys(self) -> list[str]:
        """Cache keys a consumer should invalidate for this delta.

        One key per affected file (``kg:file:<path>``) and per affected symbol
        (``kg:symbol:<id>``) — the granularity a KG-query / retrieval cache keys on.
        """
        keys = [f"kg:file:{path}" for path in self.affected_files]
        keys += [f"kg:symbol:{sid}" for sid in self.affected_symbols]
        return keys


# A cache-invalidation hook receives the keys to drop. Plain callable so the KG
# never imports the Cache subsystem (avoids the classic cache import cycle).
CacheInvalidationHook = Callable[[list[str]], None]


class CacheInvalidationRegistry:
    """Holds invalidation hooks the KG fires on graph mutation (KG-CONV).

    The KG owns one registry; the Cache/retrieval layers register a callback that
    drops the supplied keys. Firing degrades gracefully — a raising hook never
    breaks indexing.
    """

    def __init__(self) -> None:
        self._hooks: list[CacheInvalidationHook] = []

    def register(self, hook: CacheInvalidationHook) -> None:
        """Register a hook called with the keys to invalidate on each mutation."""
        self._hooks.append(hook)

    def fire(self, delta: GraphDelta) -> int:
        """Fire every hook with ``delta.cache_keys()``. Returns hooks invoked.

        A non-empty delta with no hooks is a no-op; a hook that raises is isolated
        so one bad consumer cannot break the index pass.
        """
        if delta.is_empty():
            return 0
        keys = delta.cache_keys()
        fired = 0
        for hook in self._hooks:
            try:
                hook(keys)
                fired += 1
            except Exception:
                continue
        return fired
