"""Local Studio launch + headless degrade (PR-014, SPEC-STU-014-01).

``serve`` binds ``127.0.0.1``, always prints the dashboard URL, optionally opens
a browser, and degrades cleanly when no browser/server runtime is available —
mirroring ``tui/app.py:run_cockpit_tui``'s non-TTY return contract. ``uvicorn``
is imported lazily so the rest of the runtime never depends on it.
"""

from __future__ import annotations

import contextlib
import webbrowser
from pathlib import Path


def studio_url(port: int) -> str:
    """Canonical local Studio URL for *port*."""
    return f"http://127.0.0.1:{port}"


def serve(
    root: Path | str = ".",
    port: int = 8765,
    *,
    open_browser: bool = True,
    _run: bool = True,
) -> str:
    """Start the local read-only Studio server, returning the bound URL.

    Always prints the URL first. When ``open_browser`` is set, attempts to open
    the default browser (silently degrading if none is available). When
    ``uvicorn`` is not installed, prints the URL and returns without raising
    (headless degrade). ``_run=False`` builds the app and returns the URL
    without blocking — used by tests and the no-browser smoke path.
    """
    from opencontext_core.studio.app import create_app

    app = create_app(root)
    url = studio_url(port)
    print(f"OpenContext Studio -> {url}")
    print("  Read-only control plane over .opencontext/ run evidence. Press Ctrl+C to stop.")

    if open_browser:
        with contextlib.suppress(Exception):
            webbrowser.open(url)

    if not _run:
        return url

    try:
        import uvicorn  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        print(
            "  (uvicorn is not installed — install 'uvicorn' to run the server; "
            "the read-only API and data layer are otherwise ready.)"
        )
        return url

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return url
