"""Public run contract shared by the CLI ``run`` path and MCP ``opencontext_run``.

PR-013 (SPEC-CLI-013-15/17). Both interfaces dispatch through
``runtime.api.RuntimeApi.run`` and render the SAME structured contract — no more
bare counts. The contract always carries every key (present even when empty) so
clients can rely on its shape; cost/confidence fill in as PR-011 Runtime
Intelligence lands (rendered, defaulted-empty until then).

The builder reads the legacy ``HarnessRunResult`` defensively via ``getattr`` so
it does not hard-depend on harness internals (keeps L1 below the harness in the
layer map).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_OK_STATES = {"passed", "warning", "skipped", "completed", "ok"}


class RunContract(BaseModel):
    """The full run contract returned by ``opencontext_run`` / CLI run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.run_contract.v1"
    session_id: str
    run_id: str
    workflow: str
    status: str
    summary: str = ""
    artifacts: dict[str, Any] = Field(default_factory=dict)
    receipts: dict[str, Any] = Field(default_factory=dict)
    gates: dict[str, Any] = Field(default_factory=dict)
    cost: dict[str, Any] = Field(default_factory=dict)
    confidence: dict[str, Any] = Field(default_factory=dict)
    next_recommended: str | None = None
    warnings: list[str] = Field(default_factory=list)
    # Back-compat: the MCP sampling path reports whether the host model was used.
    host_model_used: bool = False


def _status_text(value: Any) -> str:
    return str(getattr(value, "value", value)).lower() if value is not None else "completed"


def _artifacts(legacy: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for art in getattr(legacy, "artifacts", []) or []:
        path = getattr(art, "path", None) or (art if isinstance(art, str) else None)
        if path is None:
            continue
        out[str(path)] = {"path": str(path), "kind": getattr(art, "kind", None)}
    return out


def _gates(legacy: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for gate in getattr(legacy, "gates", []) or []:
        gate_id = getattr(gate, "id", None) or getattr(gate, "gate", None)
        if gate_id is None:
            continue
        status = _status_text(getattr(gate, "status", None))
        out[str(gate_id)] = {
            "status": status,
            "passed": status in _OK_STATES,
            "phase": getattr(gate, "phase", None),
            "message": getattr(gate, "message", "") or "",
            "blocking": bool(getattr(gate, "blocking", False)),
        }
    return out


def _receipts(legacy: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for idx, receipt in enumerate(getattr(legacy, "receipts", []) or []):
        out[str(getattr(receipt, "id", idx))] = (
            receipt if isinstance(receipt, str | int | float | bool) else str(receipt)
        )
    return out


def build_run_contract(
    *,
    session_id: str,
    run_id: str,
    workflow: str,
    status: str,
    legacy: Any = None,
    host_model_used: bool = False,
    cost: dict[str, Any] | None = None,
    confidence: dict[str, Any] | None = None,
) -> RunContract:
    """Build the public :class:`RunContract` from a runtime/legacy run result."""
    gates = _gates(legacy)
    failed = status not in _OK_STATES or any(not g["passed"] for g in gates.values())
    summary = str(getattr(legacy, "summary", "") or getattr(legacy, "task", "") or "")
    next_recommended = (
        "inspect the run with 'opencontext runs show " + run_id + "' and retry"
        if failed
        else "review artifacts and run 'opencontext quality --scope diff'"
    )
    return RunContract(
        session_id=session_id,
        run_id=run_id,
        workflow=workflow,
        status=status,
        summary=summary,
        artifacts=_artifacts(legacy),
        receipts=_receipts(legacy),
        gates=gates,
        cost=dict(cost or {}),
        confidence=dict(confidence or {}),
        next_recommended=next_recommended,
        warnings=list(getattr(legacy, "warnings", []) or [])[:10],
        host_model_used=host_model_used,
    )
