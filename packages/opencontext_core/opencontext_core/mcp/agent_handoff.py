"""Agent-execute handoff for MCP clients that cannot sample.

Sampling-capable MCP clients (OpenCode, ...) drive OC Flow / SDD with their own
selected model via ``sampling/createMessage`` — zero provider config. Clients
WITHOUT the ``sampling`` capability (notably Claude Code and Codex) used to
dead-end in ``status: needs_executor`` when no provider was configured.

This module turns that dead-end into a WORKING handoff: ``opencontext_run``
returns ``status: "agent_execute"`` with the frozen task contract, a
budget-bounded context-envelope summary, an ordered instruction list, and the
EXACT follow-up tool call. The client agent makes the edits itself, then calls
``opencontext_session_apply`` with ``kind="agent_edits"`` so OpenContext runs
its inspection/verification gates, records receipts, and completes the run.
The OC Flow run's evidence spine (state.json + artifacts) persists as today and
stays resumable until the follow-up completes it (see
:meth:`opencontext_core.runtime.api.RuntimeApi.apply`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

AGENT_EXECUTE_STATUS = "agent_execute"

# Budget bounds for the context summary embedded in the handoff — the agent can
# always pull more via opencontext_context; the handoff must stay small.
_MAX_CONTEXT_ITEMS = 20
_MAX_ITEM_SUMMARY_CHARS = 200

_FOLLOW_UP_TOOL = "opencontext_session_apply"


def provider_is_mock(config: Any) -> bool:
    """True when the resolved config declares no real default provider."""
    default = getattr(getattr(config, "models", None), "default", None)
    provider = getattr(default, "provider", "mock")
    return str(provider or "mock") == "mock"


def build_oc_flow_agent_handoff(
    *, root: Path, task: str, summary: dict[str, Any]
) -> dict[str, Any]:
    """Build the agent_execute handoff for a ``needs_executor`` OC Flow run.

    The run already persisted its evidence spine (task-contract.json,
    context-envelope.json, state.json with ``status: needs_executor``); this
    restores those artifacts, starts a runtime session for the follow-up tools,
    and returns the handoff keys the MCP run contract is enriched with.
    """
    flow_session_id = str(summary.get("session_id") or "")
    flow_run_id = str(summary.get("run_id") or "")
    contract_dump: dict[str, Any] | None = None
    context = _empty_context()
    try:
        from opencontext_core.oc_flow.runner import OCFlowRunner

        resumed = OCFlowRunner(root=root).resume(flow_session_id, flow_run_id)
        contract_dump = resumed.contract.model_dump()
        if resumed.envelope is not None:
            context = _context_summary(resumed.envelope)
    except Exception:
        # The handoff stays actionable even if the run artifacts are missing;
        # the agent still gets the task, instructions and follow-up call.
        pass

    oc_flow_ref = {"session_id": flow_session_id, "run_id": flow_run_id}
    session_id = _start_follow_up_session(root, task, oc_flow=oc_flow_ref)
    payload: dict[str, Any] = {
        "changed_files": ["<relative paths of every file you edited>"],
        "oc_flow": oc_flow_ref,
    }
    return {
        "status": AGENT_EXECUTE_STATUS,
        "next_recommended": AGENT_EXECUTE_STATUS,
        "session_id": session_id,
        "task": task,
        "reason": (
            "no provider is configured and this MCP client did not advertise the "
            "'sampling' capability, so OpenContext cannot run a model itself; "
            "the client agent executes the edits and OpenContext verifies + records them"
        ),
        "task_contract": contract_dump,
        "context": context,
        "instructions": _instructions(has_flow_run=True),
        "follow_up": _follow_up(root, session_id, payload),
        "oc_flow_run": {
            **oc_flow_ref,
            "resume_token": f"{flow_session_id}/{flow_run_id}",
        },
    }


def build_workflow_agent_handoff(
    *, root: Path, task: str, workflow: str, session_id: str, prior_status: str
) -> dict[str, Any]:
    """Agent_execute handoff for a non-OC-Flow (SDD) MCP run without a model.

    The harness already ran without an executor (no sampler, no provider) and
    finished in ``prior_status``; the session it ran under is reused for the
    follow-up so all evidence lands on one spine.
    """
    payload: dict[str, Any] = {
        "changed_files": ["<relative paths of every file you edited>"],
    }
    context = _empty_context()
    context["hint"] = (
        "call opencontext_context (or `opencontext pack`) with the task to build context"
    )
    return {
        "status": AGENT_EXECUTE_STATUS,
        "next_recommended": AGENT_EXECUTE_STATUS,
        "harness_status": prior_status,
        "session_id": session_id,
        "task": task,
        "reason": (
            f"the '{workflow}' workflow ran without an executor (no provider configured, "
            "MCP client without the 'sampling' capability) and ended "
            f"'{prior_status}'; the client agent executes the work itself, or configures "
            "models.default.provider in opencontext.yaml and re-runs"
        ),
        "task_contract": None,
        "context": context,
        "instructions": _instructions(has_flow_run=False),
        "follow_up": _follow_up(root, session_id, payload),
    }


# ------------------------------------------------------------------ internals
def _instructions(*, has_flow_run: bool) -> list[str]:
    """The ordered playbook the client agent follows."""
    steps = [
        (
            "Read task_contract (scope, acceptance_criteria, constraints, changed_areas) "
            "and context.items (the most relevant files/symbols) below."
            if has_flow_run
            else "Build context first: call opencontext_context with the task (or run "
            '`opencontext pack . --query "<task>"`).'
        ),
        (
            "Make the required edits YOURSELF with your own editing tools, staying "
            "within the contract's changed_areas and constraints."
        ),
        (
            "Optionally record findings while you work via opencontext_session_observe "
            "(same session_id, type='agent.note')."
        ),
        (
            "When done, call opencontext_session_apply exactly as in follow_up, with "
            "payload.changed_files listing every file you modified (add "
            "payload.test_command — argv list — when a test proves the change). "
            "OpenContext verifies the edits, records receipts, and completes the run."
        ),
        (
            "If the result is inspection_failed or needs_verification, fix the issue "
            "(or supply test_command) and call opencontext_session_apply again."
        ),
    ]
    return steps


def _follow_up(root: Path, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool": _FOLLOW_UP_TOOL,
        "arguments": {
            "session_id": session_id,
            "root": str(root),
            "kind": "agent_edits",
            "payload": payload,
        },
    }


def _empty_context() -> dict[str, Any]:
    return {"items": [], "token_estimate": 0, "omitted": 0}


def _context_summary(envelope: Any) -> dict[str, Any]:
    """Project the context envelope into a budget-bounded summary (paths + refs)."""
    items = list(getattr(envelope, "items", []) or [])
    shown = [
        {
            "source": str(getattr(item, "source", "")),
            "ref": str(getattr(item, "ref", "")),
            "summary": str(getattr(item, "summary", ""))[:_MAX_ITEM_SUMMARY_CHARS],
        }
        for item in items[:_MAX_CONTEXT_ITEMS]
    ]
    return {
        "items": shown,
        "token_estimate": int(getattr(envelope, "token_estimate", 0) or 0),
        "omitted": max(0, len(items) - _MAX_CONTEXT_ITEMS),
    }


def _start_follow_up_session(root: Path, task: str, *, oc_flow: dict[str, Any]) -> str:
    """Start the runtime session the follow-up tools operate on, linked to the run."""
    from opencontext_core.runtime.api import RuntimeApi, RuntimeEventInput, StartSessionRequest

    api = RuntimeApi(root=root)
    ref = api.start_session(StartSessionRequest(task=task, root=str(root)))
    api.observe(
        ref.session_id,
        RuntimeEventInput(
            type="agent_execute.handoff",
            status="ok",
            message="run handed off to the client agent (no provider, no sampling)",
            metadata={"oc_flow": oc_flow},
        ),
    )
    return ref.session_id
