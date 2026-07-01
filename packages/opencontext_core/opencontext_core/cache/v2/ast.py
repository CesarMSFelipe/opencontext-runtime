"""Cache v2 — `AstCacheEntry` keyed by `file_hash + symbol_path`."""

from __future__ import annotations

import hashlib

from opencontext_core.cache.base import CacheEntry, CacheType


def ast_key(file_path: str, symbol_path: str) -> str:
    """Deterministic key: ``sha256(file_path + symbol_path)``."""
    payload = f"{file_path}\x00{symbol_path}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def is_file_hash_match(stored: str, current: str) -> bool:
    """Return True if ``current`` matches the stored file_hash fingerprint."""
    return stored == current and stored != ""


class AstCacheEntry(CacheEntry):
    """AST-cache entry, keyed by file_hash + symbol_path (REQ-cache-v2-003)."""

    cache_type: CacheType = CacheType.ast
    file_path: str = ""
    file_hash: str = ""
    symbol_path: str = ""

    @classmethod
    def build(
        cls,
        *,
        file_path: str,
        file_hash: str,
        symbol_path: str,
        value_ref: str,
    ) -> "AstCacheEntry":
        return cls(
            key=ast_key(file_path, symbol_path),
            value_ref=value_ref,
            file_path=file_path,
            file_hash=file_hash,
            symbol_path=symbol_path,
        )


__all__ = ["AstCacheEntry", "ast_key", "is_file_hash_match"]