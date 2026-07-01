"""commit-012: v2 Studio control plane (FastAPI).

Six read-only endpoints that surface public contract data with
redaction applied at the response boundary. The endpoints are
intentionally stubs: they return the schema, no real provider wiring
(commit-013 supplies the real reads). The host (FastAPI) is reused via
the existing ``opencontext_api`` dependency so this commit introduces
no new external deps.
"""

from __future__ import annotations

import threading
from typing import Any

from fastapi import FastAPI

from opencontext_studio.redaction import mask


def _payload(status: str = "ok", **fields: Any) -> dict[str, Any]:
    """Compose a response payload and run it through the redaction mask."""
    body: dict[str, Any] = {"status": status}
    body.update(fields)
    masked: dict[str, Any] = mask(body)
    return masked


def create_v2_app() -> FastAPI:
    """Build the v2 Studio FastAPI app (six read-only endpoints)."""
    app = FastAPI(title="opencontext-studio-v2")

    @app.get("/api/v2/health")
    def health() -> dict[str, Any]:
        return _payload(status="ok", version="v2")

    @app.get("/api/v2/decision_log/{decision_id}")
    def decision_log(decision_id: str) -> dict[str, Any]:
        return _payload(decision_id=decision_id, rationale="stub")

    @app.get("/api/v2/brain_state")
    def brain_state() -> dict[str, Any]:
        return _payload(workflow="stub", persona="stub", skill="stub", context="stub")

    @app.get("/api/v2/capability_graph")
    def capability_graph() -> dict[str, Any]:
        return _payload(available=[], missing=[], degraded=[], install_hint={})

    @app.get("/api/v2/context_budget")
    def context_budget() -> dict[str, Any]:
        return _payload(used_tokens=0, available_tokens=0, included_refs=0, omitted_refs=0)

    @app.get("/api/v2/cache_metrics")
    def cache_metrics() -> dict[str, Any]:
        return _payload(hit_rate=0.0, miss_rate=0.0, evictions=0, top_keys=[])

    @app.get("/api/v2/learning_candidates")
    def learning_candidates() -> dict[str, Any]:
        return _payload(candidates=[], evidence=[], promotion_status="allowed")

    return app


class V2StudioServer:
    """Threaded uvicorn-style wrapper around the v2 FastAPI app.

    The server lazy-imports ``uvicorn`` (the gateway host) so test code
    that only needs the ASGI app — not the listener — does not pull in a
    networking dependency.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self._app = create_v2_app()
        self._server: Any = None
        self._thread: threading.Thread | None = None

    @property
    def app(self) -> FastAPI:
        return self._app

    @property
    def bound_port(self) -> int:
        if self._server is None:
            raise RuntimeError("v2 server not started")
        # uvicorn.Server.servers[0].sockets[0].getsockname()[1]
        sockets = getattr(self._server, "servers", []) or []
        for srv in sockets:
            for sock in getattr(srv, "sockets", []) or []:
                return int(sock.getsockname()[1])
        return self.port

    def start(self) -> None:
        import uvicorn  # type: ignore[import-not-found]  # optional [studio] extra

        config = uvicorn.Config(self._app, host=self.host, port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)

    def serve_forever(self) -> None:
        if self._server is None:
            self.start()
        import asyncio

        def _run() -> None:
            asyncio.run(self._server.serve())

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None


__all__ = ["V2StudioServer", "create_v2_app"]
