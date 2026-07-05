"""Studio — PR-014 dashboard, 11 timelines, 6 views.

``serve()`` is a minimal stdlib HTTP entry point used by the CLI; the full
FastAPI/studio surface lives in :mod:`opencontext_studio` (v2).
"""

from __future__ import annotations

import sys
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass
class TimelineEntry:
    timestamp: str
    event: str
    source: str


@dataclass
class StudioTimeline:
    name: str
    entries: list[TimelineEntry] = field(default_factory=list)


TIMELINE_NAMES = [
    "sdd-phases",
    "memory-saves",
    "conflicts",
    "judgments",
    "decisions",
    "benchmarks",
    "plugins",
    "providers",
    "cache-hits",
    "errors",
    "health",
]

VIEW_NAMES = ["dashboard", "sdd-flow", "memory-graph", "cost-breakdown", "health-radar", "timeline"]


class StudioServer:
    def status(self) -> dict[Any, Any]:
        return {"studio": "running", "timelines": len(TIMELINE_NAMES), "views": len(VIEW_NAMES)}

    def list_timelines(self) -> list[str]:
        return list(TIMELINE_NAMES)

    def list_views(self) -> list[str]:
        return list(VIEW_NAMES)


def studio_url(port: int, host: str = "127.0.0.1") -> str:
    """Return the canonical http URL for a local Studio server."""
    return f"http://{host}:{port}"


class _StudioHandler(BaseHTTPRequestHandler):
    """Default stdlib handler — just confirms the server is alive."""

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"opencontext studio")

    def log_message(self, format: str, *args: object) -> None:  # pragma: no cover - silence
        return


def serve(
    root: Any = None,
    *,
    port: int = 8765,
    open_browser: bool = True,
    _run: bool = True,
) -> str:
    """Start the local Studio server and return the bound URL.

    The full FastAPI surface lives in :mod:`opencontext_studio` (v2); this
    stdlib-only entry point keeps the CLI runnable when only a minimal
    HTTP entry is required.

    ``root`` is accepted for API symmetry with the v2 surface and is
    currently informational — the stdlib handler is root-independent.

    ``_run=False`` skips ``serve_forever`` so tests can bind + assert the
    URL without blocking (SPEC-STU-014-12).
    """
    del root  # NOTE: stdlib handler is root-agnostic

    url = studio_url(port)
    print(url, file=sys.stdout, flush=True)

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass  # NOTE: degrade silently when no display

    if not _run:
        return url

    server = ThreadingHTTPServer(("127.0.0.1", port), _StudioHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return url


__all__ = [
    "TIMELINE_NAMES",
    "VIEW_NAMES",
    "StudioServer",
    "StudioTimeline",
    "TimelineEntry",
    "serve",
    "studio_url",
]  # NOTE: stable order for commit-023
