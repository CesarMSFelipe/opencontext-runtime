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

    Manages FileWatcher lifecycle, debounces bursts of file events, and
    triggers an index callback (typically ``OpenContextRuntime.index_project``)
    for changed files.

    Usage::

        service = WatchService(
            root="/path/to/project",
            index_callback=lambda: runtime.index_project(),
        )
        service.start()
        ...
        service.stop()
    """

    def __init__(
        self,
        root: str | Path,
        index_callback: Callable[[], Any],
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
            index_callback: Zero-argument callable invoked when files change.
                Typically ``OpenContextRuntime.index_project`` bound to a root.
            debounce_seconds: Seconds to wait after the *last* file event
                before triggering a re-index.
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
        """Handle a single file event from the FileWatcher.

        Records the event timestamp and logs. The actual re-index is
        triggered by ``_debounce_check()`` after ``debounce_seconds``
        of inactivity.
        """
        self._last_event_time = time.time()
        logger.debug("File %s: %s", event_type, rel_path)

    def _debounce_and_reindex(self) -> bool:
        """Check if enough time has passed since the last event and re-index.

        Returns:
            True if a re-index was triggered, False otherwise.
        """
        if not self._running:
            return False
        if self._last_event_time == 0:
            return False

        elapsed = time.time() - self._last_event_time
        if elapsed >= self.debounce_seconds:
            logger.info(
                "Change detected — re-indexing %s (%.1fs since last event)",
                self.root,
                elapsed,
            )
            try:
                self.index_callback()
            except Exception:
                logger.exception("Re-index failed for %s", self.root)
            self._last_event_time = 0.0
            return True
        return False

    def force_reindex(self) -> None:
        """Immediately trigger a re-index regardless of debounce timer."""
        if not self._running:
            return
        logger.info("Forced re-index for %s", self.root)
        try:
            self.index_callback()
        except Exception:
            logger.exception("Forced re-index failed for %s", self.root)
        self._last_event_time = 0.0
