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
from opencontext_core.llm.provider_gateway import build_adapter, build_provider_gateway
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.nodes import NodeExecutor, ProviderBackedNodeExecutor
from opencontext_core.oc_flow.runner import OCFlowRunner
from opencontext_core.operating_model.receipts import RunReceiptStore
from opencontext_core.providers.detect import detect_provider
from opencontext_core.providers.gateway import ProviderGateway


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

    When no executor is injected (the live CLI path) this resolves one from the
    ambient environment via :func:`_resolve_executor`: a real (non-mock) provider
    yields a provider-backed executor that produces an actual edit; no provider keeps
    the executor absent so mutation tasks stay honestly ``needs_executor`` (VDM-005).
    """
    summary: dict[str, Any]
    if not enabled:
        summary = {
            "status": "disabled",
            "message": "OC Flow is off; enable it with runtime.oc_flow_enabled: true",
        }
        _maybe_print(summary, as_json)
        return summary

    # An explicitly injected executor (tests / embedders) always wins; otherwise
    # detect a real provider and build the productive executor for the live path.
    if executor is None:
        executor = _resolve_executor(root)

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
        # OC Flow hands off broad/high-risk tasks to SDD. Emit a STRUCTURED handoff so
        # `--json` consumers can branch on `workflow`/`recommended_command` rather than
        # parsing the human message (GAP 3).
        recommended_command = "opencontext harness run --workflow sdd"
        summary = {
            "status": "recommend_sdd",
            "workflow": "sdd",
            "message": f"task looks broad/high-risk; use SDD: {recommended_command}",
            "selection_reason": selection_reason,
            "recommended_command": recommended_command,
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


def _resolve_executor(root: Path) -> NodeExecutor | None:
    """Build a productive provider-backed executor when a real provider is detected.

    Reads the ambient environment via :func:`detect_provider`. When a non-mock
    provider is available it composes the PR-012 :class:`ProviderGateway` (run
    receipts + bounded local-first fallback) over a base gateway bound to that
    provider, then returns a :class:`ProviderBackedNodeExecutor` so a mutation task
    produces a REAL ``ApplyEdit`` (VDM-005). When no provider is detected (``mock``)
    — or the detected provider has no buildable adapter (e.g. ``google``/``mistral``)
    — it returns ``None`` so the runner falls back to the model-free
    ``DeterministicNodeExecutor`` and a mutation task is reported honestly as
    ``needs_executor`` (never a false ``completed`` with empty ``changed_files`` —
    B1/B8). The full provider -> validate -> policy -> checkpoint -> apply -> receipt
    -> inspection -> verify pipeline lives in ``ProviderBackedNodeExecutor``.
    """
    det = detect_provider()
    if det.name == "mock":
        return None
    base = build_provider_gateway(det.name, det.model)
    if base is None:
        return None
    gateway = ProviderGateway(
        base,
        receipts=RunReceiptStore(root),
        fallback=True,
        adapter_factory=build_adapter,
    )
    return ProviderBackedNodeExecutor(
        gateway=gateway, root=root, provider=det.name, model=det.model
    )


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
