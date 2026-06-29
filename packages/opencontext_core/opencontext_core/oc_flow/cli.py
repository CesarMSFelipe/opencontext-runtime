"""OC Flow CLI glue (PR-007, FLOW-16, book §25).

Keeps the bulk of the ``opencontext run`` execution path inside the OC Flow package
so the CLI command surface (``opencontext_cli``) stays a thin dispatcher. Resolves
``--workflow auto`` to OC Flow for localized tasks (recommending SDD when the task
is broad/high-risk), runs OC Flow to completion, or resumes a prior run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from opencontext_core.context.planning.workflow_selector import select_workflow
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.nodes import NodeExecutor
from opencontext_core.oc_flow.runner import OCFlowRunner


def run_oc_flow_cli(
    task: str | None,
    *,
    root: Path,
    workflow: str = "oc-flow",
    lane: str = "fast",
    profile: str = "balanced",
    resume: str | None = None,
    enabled: bool = True,
    as_json: bool = False,
    executor: NodeExecutor | None = None,
) -> dict[str, Any]:
    """Execute or resume OC Flow from the CLI; returns a JSON-serialisable summary.

    ``executor`` is injectable: a productive ``ProviderBackedNodeExecutor`` /
    ``McpSamplingNodeExecutor`` can be supplied when a provider is configured;
    without one the model-free ``DeterministicNodeExecutor`` is used, so a mutation
    task with no provider is reported honestly as ``needs_executor`` (never a false
    ``completed`` — B1/B8).
    """
    summary: dict[str, Any]
    if not enabled:
        summary = {
            "status": "disabled",
            "message": "OC Flow is off; enable it with runtime.oc_flow_enabled: true",
        }
        _maybe_print(summary, as_json)
        return summary

    runner = OCFlowRunner(root=root, enabled=enabled, executor=executor)

    if resume:
        # resume token is "<session_id>/<run_id>" or just "<run_id>" (latest session).
        session_id, _, run_id = resume.partition("/")
        if not run_id:
            run_id = session_id
            session_id = _latest_session(root)
        resumed = runner.resume(session_id, run_id)
        summary = {
            "status": "resumed",
            "run_id": resumed.run_id,
            "session_id": resumed.session_id,
            "task": resumed.contract.scope,
            "diagnosis_attempts": len(resumed.diagnosis_attempts),
            "inspection": resumed.inspection.outcome if resumed.inspection else None,
        }
        _maybe_print(summary, as_json)
        return summary

    if task is None:
        summary = {"status": "error", "message": "a task is required for 'run'"}
        _maybe_print(summary, as_json)
        return summary

    selected = workflow
    selection_reason = "explicit --workflow oc-flow"
    if workflow == "auto":
        # The ONE shared selector — identical policy to `simulate` (B6/AVH-013).
        decision = select_workflow(task)
        selected = decision.workflow
        selection_reason = decision.reason
    if selected == "sdd":
        summary = {
            "status": "recommend_sdd",
            "message": "task looks broad/high-risk; use SDD: opencontext harness run "
            "--workflow sdd",
            "selection_reason": selection_reason,
            "task": task,
        }
        _maybe_print(summary, as_json)
        return summary

    result = runner.run(task, lane=Lane(lane), profile=profile)
    summary = {
        "status": result.status,
        "workflow": "oc-flow",
        "run_id": result.run_id,
        "session_id": result.session_id,
        "final_node": result.final_node,
        "visited": result.visited,
        "total_tokens": result.total_tokens,
        "diagnosis_attempts": result.diagnosis_attempts,
        "escalated": result.escalated,
        "graph_status": result.graph_status,
        "completion_reason": result.completion_reason,
        "mutation_required": result.mutation_required,
        "selection_reason": result.workflow_selection.get("reason", selection_reason),
        "artifacts_dir": str(result.artifacts_dir) if result.artifacts_dir else None,
    }
    if result.status != "completed":
        summary["message"] = f"{result.status}: {result.completion_reason}"
    _maybe_print(summary, as_json)
    return summary


def _latest_session(root: Path) -> str:
    sessions = root / ".opencontext" / "sessions"
    if not sessions.is_dir():
        return ""
    candidates = sorted((d for d in sessions.iterdir() if d.is_dir()), key=lambda d: d.name)
    return candidates[-1].name if candidates else ""


def _maybe_print(summary: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"OC Flow: {summary.get('status')}")
        for key in ("workflow", "run_id", "final_node", "total_tokens",
                    "diagnosis_attempts", "selection_reason", "completion_reason",
                    "message"):
            if key in summary and summary[key] is not None:
                print(f"  {key}: {summary[key]}")
