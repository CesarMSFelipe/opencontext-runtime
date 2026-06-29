"""OpenContext Studio web shell — GET-only JSON API + static UI (PR-014).

Reuses the construction style of ``opencontext_api`` but exposes **no write
route**: only ``GET`` endpoints over :class:`~opencontext_core.studio.reader.StudioReader`
plus a static mount. Every payload passes through ``studio.redaction.redact_value``
(``SinkGuard``) before it leaves the process (SPEC-STU-014-11). This module
imports FastAPI, so it is imported lazily by the CLI/server — never at
``opencontext_core`` import time (SPEC-STU-014-12).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from opencontext_core.studio.reader import StudioReader
from opencontext_core.studio.redaction import redact_value

_STATIC = Path(__file__).parent / "static"

# Per-session read-only views dispatched by the ``{view}`` path segment. Each
# entry is a no-argument-besides-sid reader method returning a pydantic view.
_VIEWS = (
    "timeline",
    "timelines",
    "context",
    "kg",
    "memory",
    "receipts",
    "harness",
    "cost",
    "decisions",
    "brain",
    "cache",
    "learning",
)


def _payload(model: Any) -> Any:
    """Redact every string leaf of a view model's JSON projection."""
    return redact_value(model.model_dump(mode="json"))


def create_app(root: Path | str = ".") -> FastAPI:
    """Build the read-only Studio FastAPI app bound to *root*.

    NOTE: registers only ``GET`` routes and a static mount — no POST/PUT/DELETE/
    PATCH, so Studio cannot change ``.opencontext/`` files (SPEC-STU-014-11).
    """
    app = FastAPI(title="OpenContext Studio", version="0.1.0")
    reader = StudioReader(root)  # the only data boundary

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "read_only": True}

    @app.get("/api/sessions")
    def sessions() -> Any:
        return [redact_value(s.model_dump(mode="json")) for s in reader.list_sessions()]

    @app.get("/api/sessions/{sid}")
    def session(sid: str) -> Any:
        result = reader.session(sid)
        if result is None:
            raise HTTPException(status_code=404, detail=f"session not found: {sid}")
        return _payload(result)

    @app.get("/api/sessions/{sid}/{view}")
    def view(sid: str, view: str) -> Any:
        if view not in _VIEWS:
            raise HTTPException(status_code=404, detail=f"unknown view: {view}")
        return _payload(getattr(reader, "decision_log" if view == "decisions" else view)(sid))

    @app.get("/api/capabilities")
    def capabilities() -> Any:
        return _payload(reader.capabilities())

    @app.get("/api/config")
    def config() -> Any:
        return _payload(reader.config_view())

    # N2 read-only surfacing (AVH-019): project-level panels.
    @app.get("/api/tasks")
    def tasks() -> Any:
        return _payload(reader.task_history())

    @app.get("/api/release-gate")
    def release_gate() -> Any:
        return _payload(reader.release_gate())

    @app.get("/api/benchmark-coverage")
    def benchmark_coverage() -> Any:
        return _payload(reader.benchmark_coverage())

    if _STATIC.exists():
        app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="ui")
    else:  # pragma: no cover - static bundle always ships, but degrade cleanly

        @app.get("/")
        def _root() -> JSONResponse:
            return JSONResponse({"studio": "ok", "ui": "unavailable", "api": "/api/sessions"})

    return app
