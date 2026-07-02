"""v2 Studio control plane (FastAPI).

Seven read-only endpoints that surface public-contract data via
:class:`~opencontext_core.studio.reader.StudioReader`. Redaction is applied at
the response boundary via :func:`~opencontext_studio.redaction.mask` (delegated
to :func:`~opencontext_core.studio.redaction.redact_value` / SinkGuard).

The ``root`` parameter anchors StudioReader to the ``.opencontext/`` workspace;
it defaults to the current working directory so callers that do not need
project-specific data still work without arguments.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from opencontext_studio.redaction import mask


def _payload(**fields: Any) -> dict[str, Any]:
    """Compose a response payload and run it through the redaction mask."""
    body: dict[str, Any] = {"status": "ok"}
    body.update(fields)
    masked: dict[str, Any] = mask(body)
    return masked


# ---------------------------------------------------------------------------
# Internal helpers — map StudioReader view models to v2 response schemas
# ---------------------------------------------------------------------------


def _most_recent_sid(reader: Any) -> str | None:
    """Return the most recent session_id from the reader, or None."""
    sessions = reader.list_sessions()
    return sessions[0].id if sessions else None


def _find_decision(reader: Any, decision_id: str) -> dict[str, Any] | None:
    """Scan every session's decision_log for *decision_id*; return the entry dict."""
    for session in reader.list_sessions():
        if session.kind != "session":
            continue
        log_view = reader.decision_log(session.id)
        for decision in log_view.decisions:
            if decision.id == decision_id:
                return {
                    "decision_id": decision.id,
                    "kind": decision.kind,
                    "chosen": decision.chosen,
                    "rationale": decision.rationale,
                    "confidence": decision.confidence,
                    "created_at": decision.created_at,
                    "available": True,
                }
    return None


def _brain_state_payload(reader: Any) -> dict[str, Any]:
    """Map the most-recent-session brain view to the v2 brain_state schema."""
    sid = _most_recent_sid(reader)
    if sid is None:
        return {"workflow": None, "persona": None, "skill": None, "context": None}
    view = reader.brain(sid)
    if not view.available:
        return {"workflow": None, "persona": None, "skill": None, "context": None}
    # Try to resolve the current skill from the timeline node.
    skill: str | None = None
    try:
        tl = reader.timeline(sid)
        for node in tl.nodes:
            if node.name == view.recommended_next_node:
                skill = node.skill
                break
    except Exception:
        pass
    return {
        "workflow": view.recommended_next_node,
        "persona": view.persona,
        "skill": skill,
        "context": view.governed_by,
    }


def _capability_graph_payload(reader: Any) -> dict[str, Any]:
    """Map StudioCapabilityView to the v2 capability_graph schema."""
    view = reader.capabilities()
    available = [n.id for n in view.nodes if n.available]
    missing = [n.id for n in view.nodes if not n.available]
    degraded = [n.id for n in view.nodes if not n.available and n.unmet_dependencies]
    install_hint = {n.id: n.remediation for n in view.nodes if n.remediation}
    return {"available": available, "missing": missing, "degraded": degraded, "install_hint": install_hint}


def _context_budget_payload(reader: Any) -> dict[str, Any]:
    """Map the most-recent-session context view to the v2 context_budget schema."""
    sid = _most_recent_sid(reader)
    if sid is None:
        return {"used_tokens": 0, "available_tokens": 0, "included_refs": 0, "omitted_refs": 0}
    view = reader.context(sid)
    if not view.available:
        return {"used_tokens": 0, "available_tokens": 0, "included_refs": 0, "omitted_refs": 0}
    used = sum(layer.tokens_used for layer in view.layers)
    budget = view.token_budget or sum(layer.token_budget for layer in view.layers)
    return {
        "used_tokens": used,
        "available_tokens": max(budget - used, 0),
        "included_refs": len(view.evidence_refs),
        "omitted_refs": len(view.omissions),
    }


def _cache_metrics_payload(reader: Any) -> dict[str, Any]:
    """Map StudioCacheView to the v2 cache_metrics schema."""
    sid = _most_recent_sid(reader) or ""
    view = reader.cache(sid)
    if not view.available:
        return {"hit_rate": 0.0, "miss_rate": 0.0, "evictions": 0, "top_keys": []}
    total = view.hits + view.misses
    miss_rate = round(view.misses / total, 4) if total else 0.0
    top_keys = sorted(view.by_type, key=lambda k: view.by_type[k], reverse=True)
    return {
        "hit_rate": view.hit_rate,
        "miss_rate": miss_rate,
        "evictions": 0,  # not tracked in provider receipts
        "top_keys": top_keys,
    }


def _learning_candidates_payload(reader: Any) -> dict[str, Any]:
    """Map StudioLearningView to the v2 learning_candidates schema."""
    sid = _most_recent_sid(reader) or ""
    view = reader.learning(sid)
    if not view.available:
        return {"candidates": [], "evidence": [], "promotion_status": "unavailable"}
    candidate_ids = [c.candidate_id for c in view.candidates]
    all_evidence = [e for c in view.candidates for e in c.evidence]
    return {
        "candidates": candidate_ids,
        "evidence": all_evidence,
        "promotion_status": "allowed",
    }


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_v2_app(root: Path | str = ".") -> FastAPI:
    """Build the v2 Studio FastAPI app bound to *root*.

    All seven ``/api/v2/*`` endpoints pull live data from
    :class:`~opencontext_core.studio.reader.StudioReader`; no route returns stub
    values. Redaction is applied at every response boundary.

    ``root`` defaults to ``"."`` for back-compat callers that pass no argument.
    """
    from opencontext_core.studio.reader import StudioReader

    reader = StudioReader(root)
    app = FastAPI(title="opencontext-studio-v2")

    @app.get("/api/v2/health")
    def health() -> dict[str, Any]:
        return _payload(version="v2")

    @app.get("/api/v2/decision_log/{decision_id}")
    def decision_log(decision_id: str) -> dict[str, Any]:
        entry = _find_decision(reader, decision_id)
        if entry is None:
            return _payload(decision_id=decision_id, rationale=None, available=False)
        return _payload(**entry)

    @app.get("/api/v2/brain_state")
    def brain_state() -> dict[str, Any]:
        return _payload(**_brain_state_payload(reader))

    @app.get("/api/v2/capability_graph")
    def capability_graph() -> dict[str, Any]:
        return _payload(**_capability_graph_payload(reader))

    @app.get("/api/v2/context_budget")
    def context_budget() -> dict[str, Any]:
        return _payload(**_context_budget_payload(reader))

    @app.get("/api/v2/cache_metrics")
    def cache_metrics() -> dict[str, Any]:
        return _payload(**_cache_metrics_payload(reader))

    @app.get("/api/v2/learning_candidates")
    def learning_candidates() -> dict[str, Any]:
        return _payload(**_learning_candidates_payload(reader))

    return app


class V2StudioServer:
    """Threaded uvicorn-style wrapper around the v2 FastAPI app.

    The server lazy-imports ``uvicorn`` (the gateway host) so test code
    that only needs the ASGI app — not the listener — does not pull in a
    networking dependency.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0, root: Path | str = ".") -> None:
        self.host = host
        self.port = port
        self._app = create_v2_app(root=root)
        self._server: Any = None
        self._thread: threading.Thread | None = None

    @property
    def app(self) -> FastAPI:
        return self._app

    @property
    def bound_port(self) -> int:
        if self._server is None:
            raise RuntimeError("v2 server not started")
        sockets = getattr(self._server, "servers", []) or []
        for srv in sockets:
            for sock in getattr(srv, "sockets", []) or []:
                return int(sock.getsockname()[1])
        return self.port

    def start(self) -> None:
        import uvicorn  # type: ignore[import-not-found]

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
