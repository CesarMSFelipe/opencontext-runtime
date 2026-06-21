"""File watcher for auto-syncing the knowledge graph on file changes.

Supports both OS-native file events (via watchdog) and polling fallback.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Optional watchdog import
_HAS_WATCHDOG = False
try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    _HAS_WATCHDOG = True
except ImportError:
    Observer = None  # type: ignore[assignment]
    FileSystemEventHandler = object  # type: ignore[assignment,misc]
    FileSystemEvent = None  # type: ignore[assignment,misc]


class _WatchdogHandler(FileSystemEventHandler):
    """Watchdog event handler that delegates to FileWatcher callback."""

    def __init__(self, watcher: FileWatcher) -> None:
        super().__init__()
        self.watcher = watcher

    def on_modified(self, event: FileSystemEvent | None) -> None:
        if event and not event.is_directory:
            rel = self._rel_path(str(event.src_path))
            if rel and not self._is_excluded(rel):
                self.watcher.callback(rel, "modified")

    def on_created(self, event: FileSystemEvent | None) -> None:
        if event and not event.is_directory:
            rel = self._rel_path(str(event.src_path))
            if rel and not self._is_excluded(rel):
                self.watcher.callback(rel, "created")

    def on_deleted(self, event: FileSystemEvent | None) -> None:
        if event and not event.is_directory:
            rel = self._rel_path(str(event.src_path))
            if rel and not self._is_excluded(rel):
                self.watcher.callback(rel, "deleted")

    def _rel_path(self, abs_path: str) -> str | None:
        try:
            p = Path(abs_path).resolve()
            return p.relative_to(self.watcher.root).as_posix()
        except (ValueError, OSError):
            return None

    def _is_excluded(self, rel_path: str) -> bool:
        for pattern in self.watcher.exclude_patterns:
            if FileWatcher._match_pattern(rel_path, pattern):
                return True
        return False


class FileWatcher:
    """Watch files for changes and trigger callbacks.

    Uses watchdog (OS-native events) when available and requested.
    Falls back to polling-based detection with MD5 hashing.
    """

    def __init__(
        self,
        root: str | Path,
        callback: Callable[[str, str], None],
        debounce_seconds: float = 2.0,
        poll_interval: float = 1.0,
        exclude_patterns: list[str] | None = None,
        use_watchdog: bool = True,
    ) -> None:
        self.root = Path(root).resolve()
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.poll_interval = poll_interval
        self.exclude_patterns = exclude_patterns or []
        self._file_states: dict[str, tuple[int, str]] = {}
        self._pending: dict[str, float] = {}
        self._running = False
        self._use_watchdog = use_watchdog and _HAS_WATCHDOG
        self._observer: Any = None

        if use_watchdog and not _HAS_WATCHDOG:
            import warnings

            warnings.warn(
                "watchdog not installed. Falling back to polling. "
                "Install with: pip install watchdog",
                stacklevel=2,
            )

    def start(self) -> None:
        """Start watching files."""
        self._running = True

        if self._use_watchdog and _HAS_WATCHDOG:
            self._start_watchdog()
        else:
            self._scan_all()

    def _start_watchdog(self) -> None:
        """Start watchdog-based observer."""
        self._observer = Observer(timeout=self.poll_interval)
        handler = _WatchdogHandler(self)
        self._observer.schedule(handler, str(self.root), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        """Stop watching files."""
        self._running = False

        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

    def scan(self) -> list[tuple[str, str]]:
        """Scan for changes and return pending callbacks.

        In polling mode, performs a full filesystem scan.
        In watchdog mode, this is a no-op (events arrive via callbacks).

        Returns:
            List of (file_path, event_type) tuples.
        """
        if not self._running:
            return []

        # In watchdog mode, events arrive asynchronously via callbacks
        if self._use_watchdog:
            return []

        return self._polling_scan()

    def _polling_scan(self) -> list[tuple[str, str]]:
        """Polling-based change detection."""
        events: list[tuple[str, str]] = []
        now = time.time()

        # Check for modified/created files
        current_files: set[str] = set()
        for file_path in self._iter_files():
            rel_path = file_path.relative_to(self.root).as_posix()
            current_files.add(rel_path)

            mtime = file_path.stat().st_mtime
            content_hash = self._hash_file(file_path)

            if rel_path in self._file_states:
                _old_mtime, old_hash = self._file_states[rel_path]
                if old_hash != content_hash:
                    self._pending[rel_path] = now
                    self._file_states[rel_path] = (mtime, content_hash)
            else:
                self._pending[rel_path] = now
                self._file_states[rel_path] = (mtime, content_hash)

        # Check for deleted files
        for rel_path in list(self._file_states):
            if rel_path not in current_files:
                events.append((rel_path, "deleted"))
                del self._file_states[rel_path]
                if rel_path in self._pending:
                    del self._pending[rel_path]

        # Process debounced events
        for rel_path, timestamp in list(self._pending.items()):
            if now - timestamp >= self.debounce_seconds:
                events.append((rel_path, "modified"))
                del self._pending[rel_path]
                self.callback(rel_path, "modified")

        return events

    def _iter_files(self) -> Any:
        """Iterate over files in the watched directory."""
        if not self.root.exists():
            return

        for dirpath, _dirnames, filenames in os.walk(self.root):
            for filename in filenames:
                file_path = Path(dirpath) / filename
                rel_path = file_path.relative_to(self.root).as_posix()

                if self._is_excluded(rel_path):
                    continue

                yield file_path

    def _is_excluded(self, rel_path: str) -> bool:
        """Check if a relative path matches any exclude pattern."""
        for pattern in self.exclude_patterns:
            if self._match_pattern(rel_path, pattern):
                return True
        return False

    def _scan_all(self) -> None:
        """Initial scan to populate file states."""
        for file_path in self._iter_files():
            rel_path = file_path.relative_to(self.root).as_posix()
            mtime = file_path.stat().st_mtime
            content_hash = self._hash_file(file_path)
            self._file_states[rel_path] = (mtime, content_hash)

    @staticmethod
    def _hash_file(file_path: Path) -> str:
        """Compute MD5 hash of file content."""
        try:
            with open(file_path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except OSError:
            return ""

    @staticmethod
    def _match_pattern(file_path: str, pattern: str) -> bool:
        """Match a file path against a glob pattern."""
        import fnmatch

        if fnmatch.fnmatch(file_path, pattern):
            return True
        if pattern.endswith("/**"):
            prefix = pattern[:-3]
            if file_path.startswith(prefix + "/") or file_path == prefix:
                return True
        return False
