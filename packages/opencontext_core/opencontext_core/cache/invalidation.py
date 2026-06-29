"""Cache invalidation rules + file-change driven invalidator (SC-009).

An entry is dropped when a source file it depends on changes. The invalidator
subscribes to the existing ``indexing/file_watcher.py`` change callback
(``Callable[[rel_path, change], None]``) — no new watcher is introduced.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.cache.base import CacheStore, CacheType


class CacheInvalidationRule(BaseModel):
    """A rule describing when (and which) cache entries to invalidate."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Human-readable rule name.")
    trigger: Literal["file_change", "index_change", "ttl"] = Field(
        default="file_change", description="What fires this rule."
    )
    match_paths: list[str] = Field(
        default_factory=list, description="Glob patterns; empty matches any path."
    )
    cache_types: list[CacheType] = Field(
        default_factory=list, description="Cache types to invalidate; empty means all."
    )

    def matches_path(self, rel_path: str) -> bool:
        """Return True when ``rel_path`` matches this rule (empty globs = any)."""

        if not self.match_paths:
            return True
        return any(fnmatch.fnmatch(rel_path, pattern) for pattern in self.match_paths)


class CacheInvalidator:
    """Drops entries whose provenance references a changed file.

    Register :meth:`on_file_change` (or :meth:`as_callback`) with the file
    watcher; on each change it removes every entry whose
    ``provenance.source_files`` references the changed path.
    """

    def __init__(
        self,
        store: CacheStore,
        rules: list[CacheInvalidationRule] | None = None,
    ) -> None:
        self._store = store
        self._rules = (
            rules
            if rules is not None
            else [CacheInvalidationRule(name="any-file-change", trigger="file_change")]
        )

    def on_file_change(self, rel_path: str, change: str) -> int:
        """Invalidate entries referencing ``rel_path``. Returns the count removed."""

        del change  # created/modified/deleted all invalidate dependents
        applicable = [
            rule
            for rule in self._rules
            if rule.trigger == "file_change" and rule.matches_path(rel_path)
        ]
        if not applicable:
            return 0
        # If any applicable rule targets all types, do not narrow.
        type_filter: list[str] | None
        if any(not rule.cache_types for rule in applicable):
            type_filter = None
        else:
            type_filter = sorted({str(t) for rule in applicable for t in rule.cache_types})
        return self._store.invalidate_paths([rel_path], cache_types=type_filter)

    def as_callback(self) -> Callable[[str, str], None]:
        """Return a ``(rel_path, change) -> None`` callback for ``FileWatcher``."""

        def _callback(rel_path: str, change: str) -> None:
            self.on_file_change(rel_path, change)

        return _callback
