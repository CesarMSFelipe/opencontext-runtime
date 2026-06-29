"""AST parse-result cache (cache type 4 — ``ast``).

Caches parsed-symbol/edge results keyed on ``(path, content_hash)`` so unchanged
files are not re-parsed; the entry is invalidated when the file's content hash
changes (the key changes, so the old key misses).

Ponytail: this caches *parse results* (cross-run, file-invalidated). It does NOT
re-implement parser loading — the tree-sitter parser *object* is already memoized
with ``functools.lru_cache`` in ``context/signature_compression.py:_load_parser``.
This module therefore imports no tree-sitter and adds no in-process memoization.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import Field

from opencontext_core.cache.base import CacheEntry, CacheProvenance, CacheType, _hash_text
from opencontext_core.cache.store import CcrBackedCacheStore


class AstCacheEntry(CacheEntry):
    """Typed entry for a cached AST parse result, keyed on ``(path, content_hash)``."""

    cache_type: CacheType = CacheType.ast
    path: str = Field(description="Relative path of the parsed file.")


class AstCache:
    """File-invalidated AST parse-result cache over a shared store."""

    def __init__(self, store: CcrBackedCacheStore, *, enabled: bool = False) -> None:
        self._store = store
        self.enabled = enabled

    @staticmethod
    def _key(path: str, content_hash: str) -> str:
        return _hash_text(f"ast::{path}::{content_hash}")

    def get(self, path: str, content_hash: str) -> str | None:
        """Return the cached (serialized) parse result, or ``None`` on a miss."""

        if not self.enabled:
            return None
        return self._store.get_value_typed(self._key(path, content_hash), str(CacheType.ast))

    def put(
        self,
        path: str,
        content_hash: str,
        serialized_result: str,
        *,
        classification: str = "internal",
    ) -> None:
        """Store a serialized parse result for ``(path, content_hash)``."""

        if not self.enabled:
            return
        entry = AstCacheEntry(
            key=self._key(path, content_hash),
            value_ref=_hash_text(serialized_result),
            path=path,
            provenance=CacheProvenance(
                content_hash=content_hash,
                source_files={path: content_hash},
            ),
            classification=classification,
        )
        self._store.put(entry, serialized_result)

    def get_or_produce(
        self,
        path: str,
        content_hash: str,
        produce: Callable[[], str],
        *,
        classification: str = "internal",
    ) -> tuple[str, bool]:
        """Return ``(serialized_result, was_hit)``; ``produce`` (the parse) is skipped on a hit."""

        cached = self.get(path, content_hash)
        if cached is not None:
            return cached, True
        serialized_result = produce()
        self.put(path, content_hash, serialized_result, classification=classification)
        return serialized_result, False
