"""Watch service — high-level daemon for auto-syncing the knowledge graph.

Orchestrates FileWatcher lifecycle, debounces file change events, and
triggers incremental re-indexing on the OpenContext runtime.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from opencontext_core.indexing.file_watcher import FileWatcher

logger = logging.getLogger(__name__)


class WatchService:
    """High-level daemon that watches a project directory and re-indexes on change.

    Accumulates changed file paths between debounce windows and passes them to
    the index callback so callers can do incremental re-indexing instead of a
    full rebuild.

    Usage::

        def reindex(changed: set[str] | None):
            if changed:
                runtime.reindex_files(changed)
            else:
                runtime.index_project()

        service = WatchService(root=".", index_callback=reindex)
        service.start()
        ...
        service.stop()
    """

    def __init__(
        self,
        root: str | Path,
        index_callback: Callable[[set[str] | None], Any],
        *,
        debounce_seconds: float = 2.0,
        poll_interval: float = 1.0,
        exclude_patterns: list[str] | None = None,
        use_watchdog: bool = True,
        auto_start: bool = False,
    ) -> None:
        """
        Args:
            root: Project root directory to watch.
            index_callback: Called with a set of changed relative paths, or
                None when the set is unavailable (force full re-index).
            debounce_seconds: Seconds to wait after the last event.
            poll_interval: Polling interval in seconds (polling mode only).
            exclude_patterns: Glob patterns for files to ignore.
            use_watchdog: Prefer OS-native file events when available.
            auto_start: If True, call ``start()`` immediately.
        """
        self.root = Path(root).resolve()
        self.index_callback = index_callback
        self.debounce_seconds = debounce_seconds
        self._use_watchdog = use_watchdog
        self._exclude_patterns = exclude_patterns or []

        self._watcher: FileWatcher | None = None
        self._running = False
        self._poll_thread_active = False
        self._last_event_time: float = 0.0
        self._changed_paths: set[str] = set()

        if auto_start:
            self.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start watching for file changes."""
        if self._running:
            logger.debug("WatchService already running for %s", self.root)
            return

        self._watcher = FileWatcher(
            root=self.root,
            callback=self._on_file_event,
            debounce_seconds=self.debounce_seconds,
            exclude_patterns=self._exclude_patterns,
            use_watchdog=self._use_watchdog,
        )
        self._watcher.start()

        self._running = True
        self._last_event_time = 0.0
        logger.info(
            "WatchService started for %s (mode: %s)",
            self.root,
            "watchdog" if self._use_watchdog else "polling",
        )

    def stop(self) -> None:
        """Stop watching and clean up resources."""
        if not self._running:
            return

        self._running = False
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        self._poll_thread_active = False
        logger.info("WatchService stopped for %s", self.root)

    @property
    def is_running(self) -> bool:
        """Whether the service is currently running."""
        return self._running

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _on_file_event(self, rel_path: str, event_type: str) -> None:
        """Accumulate changed path and record event timestamp."""
        self._last_event_time = time.time()
        if rel_path:
            self._changed_paths.add(rel_path)
        logger.debug("File %s: %s", event_type, rel_path)

    def _debounce_and_reindex(self) -> bool:
        """Trigger incremental re-index after debounce window expires."""
        if not self._running:
            return False
        if self._last_event_time == 0:
            return False

        elapsed = time.time() - self._last_event_time
        if elapsed >= self.debounce_seconds:
            changed = self._changed_paths.copy() or None
            self._changed_paths.clear()
            self._last_event_time = 0.0
            logger.info(
                "Change detected — re-indexing %s (%s files, %.1fs since last event)",
                self.root,
                len(changed) if changed else "all",
                elapsed,
            )
            try:
                self.index_callback(changed)
            except Exception:
                logger.exception("Re-index failed for %s", self.root)
            return True
        return False

    def force_reindex(self) -> None:
        """Immediately trigger a full re-index regardless of debounce timer."""
        if not self._running:
            return
        logger.info("Forced re-index for %s", self.root)
        self._changed_paths.clear()
        self._last_event_time = 0.0
        try:
            self.index_callback(None)
        except Exception:
            logger.exception("Forced re-index failed for %s", self.root)
