"""studio — launch the local read-only Studio web control plane (PR-014).

Usage:
  opencontext studio [--port PORT] [--no-browser]

Boots the read-only Studio app against the project root and opens the
dashboard, degrading to a printed URL when no browser/TTY is available
(mirroring ``run_cockpit_tui``'s non-TTY return). Studio observes only — it
reads ``.opencontext/`` run evidence and exposes no mutating route.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def add_studio_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("studio", help="Launch the local read-only Studio web control plane.")
    p.add_argument("--port", type=int, default=8765, help="Port to bind (default: 8765).")
    p.add_argument(
        "--no-browser", action="store_true", help="Print the URL without opening a browser."
    )
    p.add_argument("--root", default=".", help="Project root to read .opencontext/ from.")


def run_studio(root: Path | str = ".", *, port: int = 8765, no_browser: bool = False) -> str:
    """Start the local Studio server; return the bound URL.

    Prefers the v2 FastAPI app (opencontext_studio.server_v2.create_v2_app)
    served via uvicorn. Falls back to the stdlib stub when either package is
    absent (ImportError).
    """
    try:
        from opencontext_studio.server_v2 import create_v2_app  # type: ignore[import]
        import uvicorn  # type: ignore[import]

        app = create_v2_app()
        uvicorn.run(app, host="127.0.0.1", port=port)
        return f"http://127.0.0.1:{port}"
    except ImportError:
        from opencontext_core.studio.server import serve

        return serve(root, port=port, open_browser=not no_browser)


def handle_studio(args: Any) -> None:
    run_studio(
        getattr(args, "root", "."),
        port=getattr(args, "port", 8765),
        no_browser=getattr(args, "no_browser", False),
    )
