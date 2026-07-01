"""FastAPI /v1/memory/* routes.

Per openspec/changes/agentic-parity-engram-gentle/design/pr3-cli-fastapi.md
§Public API additions — 17 endpoints covering save, search, session,
pin, judge, compare, delete, doctor, and more.

LB 2026 — memory API routes (PR4 wires real opencontext_memory handlers).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from opencontext_api.schemas import (
    MemoryCompareRequest,
    MemoryDeleteRequest,
    MemoryJudgeRequest,
    MemoryMergeProjectsRequest,
    MemoryPinRequest,
    MemorySaveRequest,
    MemorySessionRequest,
    MemorySessionSummaryRequest,
    MemoryTimelineRequest,
)

router = APIRouter(prefix="/v1/memory", tags=["memory"])

_VALID_RELATIONS = frozenset({
    "related", "compatible", "scoped", "conflicts_with",
    "supersedes", "not_conflict", "orphaned",
})


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


@router.post("/save")
def memory_save(body: MemorySaveRequest) -> dict:
    """Save an observation to persistent memory."""
    return {"status": "ok", "endpoint": "/v1/memory/save", "title": body.title}


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@router.get("/search")
def memory_search(query: str = Query(..., description="Search query")) -> dict:
    """Full-text BM25 search across observations."""
    return {"status": "ok", "endpoint": "/v1/memory/search", "query": query}


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


@router.get("/get/{memory_id}")
def memory_get(memory_id: str) -> dict:
    """Get full observation content by ID."""
    return {
        "status": "ok",
        "endpoint": "/v1/memory/get",
        "memory_id": memory_id,
    }


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@router.get("/context")
def memory_context() -> dict:
    """Get recent session context."""
    return {"status": "ok", "endpoint": "/v1/memory/context"}


# ---------------------------------------------------------------------------
# Save prompt
# ---------------------------------------------------------------------------


@router.post("/save-prompt")
def memory_save_prompt() -> dict:
    """Save a user prompt for context tracking."""
    return {"status": "ok", "endpoint": "/v1/memory/save-prompt"}


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


@router.get("/review")
def memory_review() -> dict:
    """Review observation lifecycle (list stale)."""
    return {"status": "ok", "endpoint": "/v1/memory/review"}


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------


@router.post("/judge")
def memory_judge(body: MemoryJudgeRequest) -> dict:
    """Record a verdict on a pending memory conflict."""
    if body.relation not in _VALID_RELATIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid relation '{body.relation}'. Valid: {sorted(_VALID_RELATIONS)}",
        )
    return {
        "status": "ok",
        "endpoint": "/v1/memory/judge",
        "judgment_id": body.judgment_id,
        "relation": body.relation,
    }


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------


@router.post("/compare")
def memory_compare(body: MemoryCompareRequest) -> dict:
    """Persist a semantic verdict into the relation store."""
    if body.relation not in _VALID_RELATIONS - {"orphaned"}:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid relation '{body.relation}' for compare. "
            f"Valid: {sorted(_VALID_RELATIONS - {'orphaned'})}",
        )
    return {
        "status": "ok",
        "endpoint": "/v1/memory/compare",
        "id_a": body.id_a,
        "id_b": body.id_b,
    }


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


@router.post("/session/start")
def memory_session_start(body: MemorySessionRequest) -> dict:
    """Register the start of a new coding session."""
    return {
        "status": "ok",
        "endpoint": "/v1/memory/session/start",
        "session_id": body.id,
    }


@router.post("/session/end")
def memory_session_end(body: MemorySessionRequest) -> dict:
    """Mark a coding session as completed."""
    return {
        "status": "ok",
        "endpoint": "/v1/memory/session/end",
        "session_id": body.id,
    }


@router.post("/session/summary")
def memory_session_summary(body: MemorySessionSummaryRequest) -> dict:
    """Save a comprehensive end-of-session summary."""
    return {"status": "ok", "endpoint": "/v1/memory/session/summary"}


# ---------------------------------------------------------------------------
# Pin / Unpin
# ---------------------------------------------------------------------------


@router.post("/pin")
def memory_pin(body: MemoryPinRequest) -> dict:
    """Pin a memory so it is never auto-pruned."""
    return {"status": "ok", "endpoint": "/v1/memory/pin", "id": body.id}


@router.post("/unpin")
def memory_unpin(body: MemoryPinRequest) -> dict:
    """Remove a pin from a memory."""
    return {"status": "ok", "endpoint": "/v1/memory/unpin", "id": body.id}


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.post("/delete")
def memory_delete(body: MemoryDeleteRequest) -> dict:
    """Delete an observation (soft delete by default)."""
    return {
        "status": "ok",
        "endpoint": "/v1/memory/delete",
        "id": body.id,
        "hard": body.hard,
    }


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------


@router.post("/doctor")
def memory_doctor() -> dict:
    """Run operational diagnostics on the memory store."""
    return {"status": "ok", "endpoint": "/v1/memory/doctor"}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@router.post("/stats")
def memory_stats() -> dict:
    """Show memory statistics."""
    return {"status": "ok", "endpoint": "/v1/memory/stats"}


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


@router.post("/timeline")
def memory_timeline(body: MemoryTimelineRequest) -> dict:
    """Show observations over time."""
    return {
        "status": "ok",
        "endpoint": "/v1/memory/timeline",
        "project": body.project,
    }


# ---------------------------------------------------------------------------
# Current project
# ---------------------------------------------------------------------------


@router.post("/current-project")
def memory_current_project() -> dict:
    """Detect the current project from working directory."""
    return {"status": "ok", "endpoint": "/v1/memory/current-project"}


# ---------------------------------------------------------------------------
# Merge projects
# ---------------------------------------------------------------------------


@router.post("/merge-projects")
def memory_merge_projects(body: MemoryMergeProjectsRequest) -> dict:
    """Merge observations from source projects into target."""
    return {
        "status": "ok",
        "endpoint": "/v1/memory/merge-projects",
        "target": body.target,
        "sources": body.sources,
    }
