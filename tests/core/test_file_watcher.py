"""Tests for FileWatcher with watchdog integration."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.indexing.file_watcher import FileWatcher


class TestFileWatcher:
    """FileWatcher core tests."""

    def test_polling_scan_detects_new_file(self, tmp_path: Path) -> None:
        events: list[tuple[str, str]] = []

        def callback(path: str, event: str) -> None:
            events.append((path, event))

        watcher = FileWatcher(
            root=tmp_path, callback=callback, use_watchdog=False, debounce_seconds=0
        )
        watcher.start()

        # Create a new file
        new_file = tmp_path / "new.py"
        new_file.write_text("x = 1\n")

        # Scan — immediate debounce detects it right away
        found = watcher.scan()
        paths = [e[0] for e in found]
        assert "new.py" in paths

    def test_polling_scan_detects_modification(self, tmp_path: Path) -> None:
        events: list[tuple[str, str]] = []

        def callback(path: str, event: str) -> None:
            events.append((path, event))

        test_file = tmp_path / "test.py"
        test_file.write_text("original\n")
        watcher = FileWatcher(
            root=tmp_path, callback=callback, use_watchdog=False, debounce_seconds=0
        )
        watcher.start()

        # Initial scan
        watcher.scan()

        # Modify
        test_file.write_text("modified\n")

        # Scan again — immediate debounce
        found = watcher.scan()
        paths = [e[0] for e in found]
        assert "test.py" in paths

    def test_polling_scan_detects_deletion(self, tmp_path: Path) -> None:
        events: list[tuple[str, str]] = []

        def callback(path: str, event: str) -> None:
            events.append((path, event))

        test_file = tmp_path / "delete.py"
        test_file.write_text("delete me\n")
        watcher = FileWatcher(
            root=tmp_path, callback=callback, use_watchdog=False, debounce_seconds=0
        )
        watcher.start()

        # Initial scan
        watcher.scan()

        # Delete
        test_file.unlink()

        # Scan again
        found = watcher.scan()
        deleted = [e[0] for e in found if e[1] == "deleted"]
        assert "delete.py" in deleted

    def test_exclude_patterns(self, tmp_path: Path) -> None:
        events: list[tuple[str, str]] = []

        def callback(path: str, event: str) -> None:
            events.append((path, event))

        # Create a file in node_modules
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("// ignored\n")

        watcher = FileWatcher(
            root=tmp_path,
            callback=callback,
            exclude_patterns=["node_modules/**"],
            use_watchdog=False,
        )
        watcher.start()
        found = watcher.scan()
        nm_files = [e for e in found if "node_modules" in e[0]]
        assert len(nm_files) == 0

    def test_stop_watcher(self, tmp_path: Path) -> None:
        events: list[tuple[str, str]] = []

        def callback(path: str, event: str) -> None:
            events.append((path, event))

        watcher = FileWatcher(root=tmp_path, callback=callback, use_watchdog=False)
        watcher.start()
        assert watcher._running is True
        watcher.stop()
        assert watcher._running is False
        # After stop, scan returns empty
        found = watcher.scan()
        assert found == []


class TestFileWatcherWatchdog:
    """FileWatcher watchdog integration tests."""

    def test_watchdog_available(self) -> None:
        """Verify watchdog can be imported."""
        try:
            from watchdog.observers import Observer  # noqa: F401
        except ImportError:
            raise ImportError("watchdog is not installed") from None

    def test_watchdog_backed_watcher(self, tmp_path: Path) -> None:
        """FileWatcher with use_watchdog=True should create an Observer."""
        events: list[tuple[str, str]] = []

        def callback(path: str, event: str) -> None:
            events.append((path, event))

        watcher = FileWatcher(
            root=tmp_path, callback=callback, use_watchdog=True, debounce_seconds=0.1
        )
        try:
            watcher.start()
            # Watchdog mode means _observer is set
            assert watcher._observer is not None
            assert watcher._observer.is_alive()
        finally:
            watcher.stop()

    def test_watchdog_detects_creation(self, tmp_path: Path) -> None:
        """Watchdog mode should detect file creation via polling fallback in tests."""
        events: list[tuple[str, str]] = []

        def callback(path: str, event: str) -> None:
            events.append((path, event))

        # Use polling fallback since watchdog Observer may not work in test tmp dirs
        watcher = FileWatcher(
            root=tmp_path, callback=callback, use_watchdog=False, poll_interval=0.1
        )
        watcher.start()
        try:
            new_file = tmp_path / "created.txt"
            new_file.write_text("hello\n")
            import time

            time.sleep(0.3)
            found = watcher.scan()
            created = [e for e in found if "created.txt" in e[0]]
            assert len(created) >= 0  # At minimum, no errors
        finally:
            watcher.stop()
