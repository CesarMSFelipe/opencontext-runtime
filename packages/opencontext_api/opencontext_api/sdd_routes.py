"""FastAPI /v1/sdd/* routes.

Per openspec/changes/agentic-parity-engram-gentle/design/pr3-cli-fastapi.md
§Public API additions — status, continue, and phase endpoints.

LB 2026 — SDD API routes.
"""

from __future__ import annotations

from fastapi import APIRouter

from opencontext_api.schemas import SDDContinueRequest, SDDPhaseRequest

router = APIRouter(prefix="/v1/sdd", tags=["sdd"])

_SDD_PHASES = frozenset({
    "explore", "propose", "spec", "design", "tasks",
    "apply", "verify", "archive",
})


@router.get("/status")
def sdd_status(change: str = "", cwd: str = ".") -> dict:
    """Resolve and return the SDD status."""
    try:
        from opencontext_sdd.status import Resolve

        status = Resolve(change, cwd=cwd)
        return status.model_dump(mode="json", exclude_none=True)
    except ImportError:
        return {
            "schemaName": "opencontext.sdd-status",
            "schemaVersion": 1,
            "changeName": change,
            "nextRecommended": "select-change",
            "blockedReasons": [],
        }


@router.post("/continue")
def sdd_continue(body: SDDContinueRequest) -> dict:
    """Continue with the next recommended phase."""
    return {
        "status": "ok",
        "prompt": f"# SDD Continue\n\nChange: {body.change}\nCwd: {body.cwd}\n(PR4 wires real runner)",
    }


@router.post("/{phase}")
def sdd_phase(phase: str, body: SDDPhaseRequest) -> dict:
    """Run an SDD phase."""
    if phase not in _SDD_PHASES:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail=f"Unknown SDD phase '{phase}'. Valid: {sorted(_SDD_PHASES)}",
        )
    return {
        "status": "ok",
        "phase": phase,
        "change": body.change,
        "cwd": body.cwd,
        "note": "PR4 wires real runner",
    }
