"""PR-014 StudioServer — stdlib-only local HTTP server on 127.0.0.1:random_port."""

from __future__ import annotations

import socket
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable


@dataclass
class StudioConfig:
    host: str = "127.0.0.1"
    port: int = 0  # random free port
    handler_factory: Callable[[], BaseHTTPRequestHandler] | None = None


class StudioServer:
    """Headless-friendly HTTP server. Use ``port=0`` to bind a random free port.

    ``start()`` binds the listening socket. ``serve_forever()`` runs the request
    loop on a daemon thread (call explicitly if you want to handle traffic).
    ``stop()`` joins the thread if it is running, then closes the server.
    """

    def __init__(self, config: StudioConfig | None = None) -> None:
        self.config = config or StudioConfig()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def bound_address(self) -> tuple[str, int]:
        if self._server is None:
            raise RuntimeError("server not started")
        host, port = self._server.server_address[:2]
        return host, port

    def start(self) -> None:
        handler = self.config.handler_factory or _default_handler
        self._server = ThreadingHTTPServer((self.config.host, self.config.port), handler)

    def serve_forever(self) -> None:
        if self._server is None:
            raise RuntimeError("server not started")
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        if self._thread is not None and self._thread.is_alive():
            self._server.shutdown()
            self._thread.join(timeout=5)
        self._server.server_close()
        self._server = None
        self._thread = None


def _default_handler() -> BaseHTTPRequestHandler:
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # pragma: no cover - default page only
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"opencontext studio")

        def log_message(self, format: str, *args: object) -> None:  # silence
            return
    return _Handler