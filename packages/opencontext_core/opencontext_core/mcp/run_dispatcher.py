"""MCP run dispatcher.

One small seam for agent hosts: OC Flow uses the same product path as the CLI,
while formal SDD workflows still go through RuntimeApi until the SDD validator
slice lands.
"""

from __future__ import annotations

import contextlib
import io
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

    Returns ``None`` for workflows not owned by this dispatcher yet.
    """

    if workflow not in {"oc-flow", "auto"}:
        return None

    with contextlib.redirect_stdout(io.StringIO()):
        summary = run_oc_flow_cli(
            task,
            root=root,
            workflow=workflow,
            lane=lane,
            profile=profile,
            enabled=True,
            as_json=False,
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
    return contract
