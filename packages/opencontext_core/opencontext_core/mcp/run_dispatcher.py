"""MCP run dispatcher — DEPRECATED shim delegating to runtime_dispatcher.

This module is a backward-compatible shim retained after the C15 spine flip.
New callers should use :mod:`opencontext_core.mcp.runtime_dispatcher` directly,
which exposes the 9-method session-first RuntimeApi surface.

C15 spine flip: ``dispatch_mcp_run`` retains the legacy ``run_oc_flow_cli``
path for backward-compatible OC Flow MCP calls.  The ``mcp-runtime`` migration
flag controls TOOL REGISTRATION (``runtime_dispatcher.registered_tools()``
returns the 9-method session API when migrated); it does NOT change this
function's routing because ``dispatch_mcp_run`` is a different entry point from
the ``runtime.*`` tool dispatcher.

Rollback for C15: revert ``state=MigrationState.migrated`` to
``state=MigrationState.legacy`` for rt-spine and mcp-runtime in
``compat/migration.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_core.llm.sampling_gateway import get_host_sampler
from opencontext_core.oc_flow.cli import run_oc_flow_cli
from opencontext_core.runtime.run_contract import build_run_contract


def dispatch_mcp_run(
    *,
    task: str,
    workflow: str,
    root: Path,
    profile: str = "balanced",
    lane: str = "fast",
) -> dict[str, Any] | None:
    """Dispatch MCP run requests that already have a current product path.

    This function is the backward-compatible OC Flow MCP entry point.  The vNext
    session-first API is exposed via ``runtime_dispatcher.registered_tools()``
    and ``runtime_dispatcher.handle_tool_call()`` once the mcp-runtime flag is
    migrated.

    Returns ``None`` for workflows not owned by this dispatcher yet.
    """

    if workflow not in {"oc-flow", "auto"}:
        return None

    # ``quiet=True`` (NOT redirect_stdout): stdout is the MCP wire here, and a
    # blanket redirect would also swallow mid-run server->client
    # ``sampling/createMessage`` requests, stalling every sampling call to its
    # timeout on a real host.
    summary = run_oc_flow_cli(
        task,
        root=root,
        workflow=workflow,
        lane=lane,
        profile=profile,
        enabled=True,
        as_json=False,
        quiet=True,
    )
    contract = build_run_contract(
        session_id=str(summary.get("session_id") or ""),
        run_id=str(summary.get("run_id") or ""),
        workflow=str(summary.get("workflow") or workflow),
        status=str(summary.get("status") or "failed"),
        host_model_used=get_host_sampler() is not None,
    ).model_dump()
    contract.update(
        {
            "selected_workflow": summary.get("workflow") or workflow,
            "verified_by": summary.get("verified_by"),
            "verification_outcome": summary.get("verification_outcome"),
            "reason": summary.get("completion_reason") or summary.get("message"),
            "oc_flow": summary,
        }
    )
    if summary.get("status") == "needs_executor" and get_host_sampler() is None:
        # No provider AND a client that cannot sample: upgrade the honest
        # dead-end into an actionable agent-execute handoff (the run's evidence
        # spine is already persisted and stays resumable).
        from opencontext_core.mcp.agent_handoff import build_oc_flow_agent_handoff

        contract.update(build_oc_flow_agent_handoff(root=root, task=task, summary=summary))
    return contract
