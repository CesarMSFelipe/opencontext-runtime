"""Cache v2 — `PromptContextCacheEntry` keyed by (task, profile, workflow, node)."""

from __future__ import annotations

import hashlib
import json

from opencontext_core.cache.base import CacheEntry, CacheType


def prompt_context_key(
    *,
    task: str,
    profile: str,
    workflow: str,
    node: str,
) -> str:
    """Deterministic key for prompt/context cache entries."""
    payload = {"node": node, "profile": profile, "task": task, "workflow": workflow}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PromptContextCacheEntry(CacheEntry):
    """Prompt/context cache entry, keyed by the (task, profile, workflow, node) tuple."""

    cache_type: CacheType = CacheType.prompt_context
    task: str = ""
    profile: str = ""
    workflow: str = ""
    node: str = ""


__all__ = ["PromptContextCacheEntry", "prompt_context_key"]
