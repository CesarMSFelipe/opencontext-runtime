"""Local semantic cache (PR-010 CTX-CONV; typed port for PR-000.3).

A conservative semantic cache keyed on task/context similarity: it returns a prior
pack when a stored entry is sufficiently similar (token-set Jaccard >= threshold) and
shares the same workflow/project when configured. Every lookup records a hit/miss and
attaches provenance. ``invalidate`` clears entries on a KG delta.

This is the concrete implementation of the ``cache/base.py:SemanticCache`` Protocol.
PR-000.3 will back it with real embeddings behind the same surface (the seam noted in
the book convergence list); the Jaccard similarity here is a deterministic stand-in.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.cache.base import (
    CacheEntry,
    CacheKey,
    CacheProvenance,
    CacheType,
    _hash_text,
    cache_allowed_for_classifications,
)
from opencontext_core.safety.redaction import SinkGuard

_WORD_RE = re.compile(r"[a-z0-9_]+")


def _tokens(text: str) -> frozenset[str]:
    return frozenset(_WORD_RE.findall(text.lower()))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class SemanticCacheEntry(CacheEntry):
    """One stored pack with similarity fields + provenance (PR-000.3 typed entry).

    Subclasses the unified :class:`CacheEntry` so it carries ``schema_version``,
    ``classification``, provenance, and hit/miss telemetry; the similarity-specific
    fields (``workflow`` / ``project_hash`` / ``text`` / ``value``) drive the
    conservative Jaccard match used by :class:`LocalSemanticCache`.
    """

    cache_type: CacheType = CacheType.semantic
    key_value: str = Field(description="Exact CacheKey hash of the stored entry.")
    workflow: str = Field(description="Workflow the entry was built for.")
    project_hash: str = Field(description="Project hash at store time (KG-delta scope).")
    text: str = Field(description="The task/context text the entry was keyed on.")
    value: str = Field(description="The cached pack/response (redacted).")


class SemanticCacheStats(BaseModel):
    """Hit/miss accounting for the semantic cache."""

    model_config = ConfigDict(extra="forbid")

    hits: int = Field(default=0, ge=0)
    misses: int = Field(default=0, ge=0)


class LocalSemanticCache:
    """In-memory semantic cache satisfying ``cache/base.py:SemanticCache``."""

    def __init__(
        self,
        *,
        similarity_threshold: float = 0.92,
        require_same_workflow: bool = True,
        require_same_project_hash: bool = True,
    ) -> None:
        self.similarity_threshold = similarity_threshold
        self.require_same_workflow = require_same_workflow
        self.require_same_project_hash = require_same_project_hash
        self._entries: list[SemanticCacheEntry] = []
        self.stats = SemanticCacheStats()
        # Provenance of the most recent hit (workflow/project/similarity), or None.
        self.last_hit_provenance: dict[str, object] | None = None

    def store(self, key: CacheKey, text: str, value: str) -> None:
        """Store a pack keyed on ``text`` (fails closed for secret/regulated)."""
        if not cache_allowed_for_classifications(key.classifications):
            return
        safe_value, _ = SinkGuard().redact(value)
        self._entries.append(
            SemanticCacheEntry(
                key=key.value,
                key_value=key.value,
                value_ref=_hash_text(safe_value),
                workflow=key.workflow_name,
                project_hash=key.project_hash,
                text=text,
                value=safe_value,
                provenance=CacheProvenance(content_hash=_hash_text(safe_value)),
            )
        )

    def lookup(self, key: CacheKey, text: str) -> str | None:
        """Return a semantically similar cached pack, or None. Records hit/miss.

        On a hit, ``last_hit_provenance`` carries the matched workflow, project hash,
        and the similarity score so callers can attach provenance to the result.
        """
        if not cache_allowed_for_classifications(key.classifications):
            self.stats.misses += 1
            self.last_hit_provenance = None
            return None

        query = _tokens(text)
        best: SemanticCacheEntry | None = None
        best_sim = 0.0
        for entry in self._entries:
            if self.require_same_workflow and entry.workflow != key.workflow_name:
                continue
            if self.require_same_project_hash and entry.project_hash != key.project_hash:
                continue
            sim = _jaccard(query, _tokens(entry.text))
            if sim > best_sim:
                best, best_sim = entry, sim

        if best is not None and best_sim >= self.similarity_threshold:
            self.stats.hits += 1
            self.last_hit_provenance = {
                "source": "semantic_cache",
                "workflow": best.workflow,
                "project_hash": best.project_hash,
                "similarity": round(best_sim, 4),
            }
            return best.value

        self.stats.misses += 1
        self.last_hit_provenance = None
        return None

    def invalidate(self, *, project_hash: str | None = None) -> int:
        """Invalidate entries on a KG delta. Returns the number dropped.

        With ``project_hash`` only that (now-changed) project's entries are dropped —
        a scoped KG delta makes them stale; without it the whole cache is cleared.
        """
        if project_hash is None:
            dropped = len(self._entries)
            self._entries.clear()
            return dropped
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.project_hash != project_hash]
        return before - len(self._entries)
