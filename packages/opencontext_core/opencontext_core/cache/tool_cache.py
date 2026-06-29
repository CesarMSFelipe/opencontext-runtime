"""Tool-output cache (cache type 3 — ``tool_output``).

Caches deterministic, read-only tool/MCP outputs keyed on
``(tool_name, normalized_args, source_fingerprint)``. Tools declared mutating /
side-effecting are NEVER cached. Disabled by default — the call site opts in via
``cache.runtime.enabled``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import Field

from opencontext_core.cache.base import CacheEntry, CacheProvenance, CacheType, _hash_text
from opencontext_core.cache.store import CcrBackedCacheStore


class ToolCacheEntry(CacheEntry):
    """Typed entry for a cached read-only tool output."""

    cache_type: CacheType = CacheType.tool_output
    tool_name: str = Field(description="The cached tool's name.")
    args_hash: str = Field(description="Hash of the normalized tool arguments.")


def _args_hash(args: Mapping[str, Any]) -> str:
    encoded = json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ToolCache:
    """Read-only tool-output cache over a shared :class:`CcrBackedCacheStore`."""

    def __init__(self, store: CcrBackedCacheStore, *, enabled: bool = False) -> None:
        self._store = store
        self.enabled = enabled

    @staticmethod
    def _key(tool_name: str, args_hash: str) -> str:
        return _hash_text(f"tool::{tool_name}::{args_hash}")

    def get(self, tool_name: str, args: Mapping[str, Any]) -> str | None:
        """Return a cached output for ``(tool_name, args)`` or ``None``."""

        if not self.enabled:
            return None
        return self._store.get_value_typed(
            self._key(tool_name, _args_hash(args)), str(CacheType.tool_output)
        )

    def put(
        self,
        tool_name: str,
        args: Mapping[str, Any],
        output: str,
        *,
        mutating: bool,
        provenance: CacheProvenance | None = None,
        classification: str = "internal",
    ) -> None:
        """Store a read-only tool output. No-op when ``mutating`` is True."""

        if not self.enabled or mutating:
            return
        args_hash = _args_hash(args)
        entry = ToolCacheEntry(
            key=self._key(tool_name, args_hash),
            value_ref=_hash_text(output),
            tool_name=tool_name,
            args_hash=args_hash,
            provenance=provenance or CacheProvenance(content_hash=_hash_text(output)),
            classification=classification,
        )
        self._store.put(entry, output)

    def get_or_produce(
        self,
        tool_name: str,
        args: Mapping[str, Any],
        produce: Callable[[], str],
        *,
        mutating: bool = False,
        provenance: CacheProvenance | None = None,
        classification: str = "internal",
    ) -> tuple[str, bool]:
        """Return ``(output, was_hit)``; ``produce`` is skipped on a hit.

        This is the real token/tool-call reduction surface: on a hit the
        underlying tool is not re-invoked.
        """

        cached = self.get(tool_name, args)
        if cached is not None:
            return cached, True
        output = produce()
        self.put(
            tool_name,
            args,
            output,
            mutating=mutating,
            provenance=provenance,
            classification=classification,
        )
        return output, False
