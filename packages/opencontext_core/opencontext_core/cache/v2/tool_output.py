"""Cache v2 — `ToolCacheEntry` keyed by `tool_name + args_hash` (mtime-invalidated)."""

from __future__ import annotations

import hashlib
import json

from opencontext_core.cache.base import CacheEntry, CacheType


def tool_key(tool_name: str, args: dict[str, object]) -> str:
    """Deterministic key: ``sha256(tool_name + sorted_args_json)``."""
    payload = {"args": args, "tool": tool_name}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _hash_args(args: dict[str, object]) -> str:
    encoded = json.dumps(args, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ToolCacheEntry(CacheEntry):
    """Tool-output cache entry; source_file_mtime drives invalidation (REQ-cache-v2-003)."""

    cache_type: CacheType = CacheType.tool_output
    tool_name: str = ""
    args_hash: str = ""
    source_file_mtime: float = 0.0

    @classmethod
    def build(
        cls,
        *,
        tool_name: str,
        args: dict[str, object],
        value_ref: str,
        source_file_mtime: float = 0.0,
    ) -> ToolCacheEntry:
        return cls(
            key=tool_key(tool_name, args),
            value_ref=value_ref,
            tool_name=tool_name,
            args_hash=_hash_args(args),
            source_file_mtime=source_file_mtime,
        )


__all__ = ["ToolCacheEntry", "tool_key"]
