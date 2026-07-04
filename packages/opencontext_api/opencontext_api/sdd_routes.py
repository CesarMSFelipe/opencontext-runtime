"""FastAPI /v1/sdd/* routes.

Per openspec/changes/agentic-parity-engram-gentle/design/pr3-cli-fastapi.md
§Public API additions — status, continue, and phase endpoints.

LB 2026 — SDD API routes.
"""

from __future__ import annotations

from fastapi import APIRouter
from opencontext_sdd.runner import run_phase

from opencontext_api.schemas import SDDContinueRequest, SDDPhaseRequest

router = APIRouter(prefix="/v1/sdd", tags=["sdd"])

_SDD_PHASES = frozenset(
    {
        "explore",
        "propose",
        "spec",
        "design",
        "tasks",
        "apply",
        "verify",
        "archive",
    }
)


@router.get("/status")
def sdd_status(change: str = "", cwd: str = ".") -> dict[str, object]:
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
def sdd_continue(body: SDDContinueRequest) -> dict[str, object]:
    """Continue with the next recommended phase."""
    try:
        from opencontext_sdd.dispatcher import RenderNativePhasePrompt

        prompt = RenderNativePhasePrompt("continue", change=body.change)
    except Exception:
        prompt = f"# SDD Continue\n\nChange: {body.change}\nCwd: {body.cwd}"
    return {
        "status": "ok",
        "prompt": prompt,
    }


@router.post("/{phase}")
def sdd_phase(phase: str, body: SDDPhaseRequest) -> dict[str, object]:
    """Run an SDD phase."""
    from fastapi import HTTPException

    if phase not in _SDD_PHASES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown SDD phase '{phase}'. Valid: {sorted(_SDD_PHASES)}",
        )
    try:
        envelope = run_phase(
            phase,
            change=body.change,
            cwd=body.cwd or ".",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"SDD phase '{phase}' failed due to an internal error.",
        ) from exc
    return envelope.model_dump(mode="json", exclude_none=True)
