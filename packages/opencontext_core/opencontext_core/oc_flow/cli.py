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

import yaml

from opencontext_core.config_resolver import resolve_config_path
from opencontext_core.context.planning.workflow_selector import select_workflow
from opencontext_core.llm.provider_gateway import build_adapter, build_provider_gateway
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.nodes import NodeExecutor, ProviderBackedNodeExecutor
from opencontext_core.oc_flow.runner import OCFlowRunner
from opencontext_core.operating_model.receipts import RunReceiptStore
from opencontext_core.paths import StorageMode, resolve_workspace_path
from opencontext_core.providers.detect import detect_provider
from opencontext_core.providers.gateway import ProviderGateway
from opencontext_core.providers.test_stub import TestStubGateway


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
    quiet: bool = False,
    executor: NodeExecutor | None = None,
) -> dict[str, Any]:
    """Execute or resume OC Flow from the CLI; returns a JSON-serialisable summary.

    ``quiet`` suppresses the human/JSON summary print entirely. Embedders that
    share stdout with a wire protocol (the MCP stdio server) MUST use it instead
    of redirecting stdout: a blanket ``redirect_stdout`` would also swallow
    server->client ``sampling/createMessage`` requests emitted mid-run, so the
    host never sees them and every sampling call stalls to its timeout.

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
        if not quiet:
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
        if not quiet:
            _maybe_print(summary, as_json)
        return summary

    if task is None:
        summary = {"status": "error", "message": "a task is required for 'run'"}
        if not quiet:
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
        if not quiet:
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
        "verified_by": result.verified_by,
        "verification_outcome": result.verification_outcome,
        "selection_reason": result.workflow_selection.get("reason", selection_reason),
        "artifacts_dir": str(result.artifacts_dir) if result.artifacts_dir else None,
    }
    if result.status != "completed":
        summary["message"] = f"{result.status}: {result.completion_reason}"
    if not quiet:
        _maybe_print(summary, as_json)
    return summary


def _resolve_executor(root: Path) -> NodeExecutor | None:
    """Build a productive provider-backed executor when a real provider is detected.

    Reads the ambient environment via :func:`detect_provider`, then consults the
    formal :class:`~opencontext_core.executors.registry.ExecutorRegistry` to build
    the executor for the resolved id (a formalization of the previously hardcoded
    resolution — behavior for existing configs is identical). When a non-mock
    provider is available the ``provider`` executor composes the PR-012
    :class:`ProviderGateway` (run receipts + bounded local-first fallback) over a
    base gateway bound to that provider, so a mutation task produces a REAL
    ``ApplyEdit`` (VDM-005). When no provider is detected (``mock``) — or the
    detected provider has no buildable adapter (e.g. ``google``/``mistral``) — it
    returns ``None`` so the runner falls back to the model-free
    ``DeterministicNodeExecutor`` and a mutation task is reported honestly as
    ``needs_executor`` (never a false ``completed`` with empty ``changed_files`` —
    B1/B8). The full provider -> validate -> policy -> checkpoint -> apply -> receipt
    -> inspection -> verify pipeline lives in ``ProviderBackedNodeExecutor``.
    """
    from opencontext_core.executors.registry import default_registry

    registry = default_registry()
    det = detect_provider()
    if det.name == "mock":
        from opencontext_core.llm.sampling_gateway import get_host_sampler

        if sampler := get_host_sampler():
            return registry.build("mcp", root=root, sampler=sampler)  # type: ignore[no-any-return]
        # TEST-ONLY gate (PROD-002 / design B2): a config that EXPLICITLY declares
        # `provider: test_stub` with a resolvable `edits_file` drives the real mutation
        # pipeline credential-free. This is NEVER a production fallback — any other
        # state (no config, no `test_stub`, or a missing / out-of-root `edits_file`)
        # falls through, exactly as the pre-change path.
        if (stub := registry.build("test_stub", root=root)) is not None:
            return stub  # type: ignore[no-any-return]
        # EXE-004: an explicit `provider: patch` + resolvable `patch_file` drives the
        # same real mutation pipeline from a unified-diff file. Never a fallback —
        # without the explicit opt-in this is None and the runner keeps the
        # model-free DeterministicNodeExecutor (`needs_executor`).
        return registry.build("patch", root=root)  # type: ignore[no-any-return]
    return registry.build(  # type: ignore[no-any-return]
        "provider", root=root, provider_name=det.name, model=det.model
    )


def _build_detected_provider_executor(
    root: Path, provider_name: str, model: str
) -> NodeExecutor | None:
    """Build the productive executor for a detected (non-mock) provider.

    Returns ``None`` when the provider has no buildable adapter, preserving the
    honest ``needs_executor`` path. Registered as the ``provider`` builder in the
    executor registry; the construction is byte-identical to the pre-registry code.
    """
    base = build_provider_gateway(provider_name, model)
    if base is None:
        return None
    gateway = ProviderGateway(
        base,
        receipts=RunReceiptStore(root),
        fallback=True,
        adapter_factory=build_adapter,
    )
    return ProviderBackedNodeExecutor(
        gateway=gateway, root=root, provider=provider_name, model=model
    )


def _resolve_test_stub_executor(root: Path) -> NodeExecutor | None:
    """Build a ``TestStubGateway``-backed executor IFF config explicitly opts in (B2).

    TEST-ONLY: returns a productive :class:`ProviderBackedNodeExecutor` ONLY when the
    resolved ``opencontext.yaml`` declares ``provider: test_stub`` AND a resolvable
    ``edits_file`` that exists under *root*. Any other state — no config, no
    ``test_stub``, a missing / non-string ``edits_file``, a file that does not exist,
    or one escaping *root* — returns ``None`` so the caller behaves EXACTLY as the
    pre-change production path. This is never a production resolver fallback; the
    no-fallthrough invariant is asserted in ``tests/oc_flow/test_test_stub_resolution.py``.
    """
    raw = _read_yaml_mapping(resolve_config_path(root, None))
    if raw.get("provider") != "test_stub":
        return None
    edits_file = raw.get("edits_file")
    if not edits_file or not isinstance(edits_file, str):
        return None
    root_resolved = root.resolve()
    resolved = (root_resolved / edits_file).resolve()
    if not resolved.is_file() or not _within(root_resolved, resolved):
        return None
    return ProviderBackedNodeExecutor(
        gateway=TestStubGateway(resolved), root=root, provider="test_stub"
    )


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    """Raw-read a YAML file's top-level mapping; ``{}`` on missing / invalid / non-mapping.

    Deliberately raw (NOT :class:`OpenContextConfig`) so the test-only ``test_stub``
    keys never enter the typed production config schema or the detect stack (B2).
    """
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _within(root: Path, candidate: Path) -> bool:
    """True iff *candidate* is *root* or lives under it (rejects ``edits_file`` escaping root)."""
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _latest_session(root: Path) -> str:
    sessions = resolve_workspace_path(root, StorageMode.local) / "sessions"
    if not sessions.is_dir():
        return ""
    candidates = sorted((d for d in sessions.iterdir() if d.is_dir()), key=lambda d: d.name)
    return candidates[-1].name if candidates else ""


def _maybe_print(summary: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"OC Flow: {summary.get('status')}")
        for key in (
            "workflow",
            "run_id",
            "final_node",
            "total_tokens",
            "diagnosis_attempts",
            "selection_reason",
            "completion_reason",
            "message",
        ):
            if key in summary and summary[key] is not None:
                print(f"  {key}: {summary[key]}")
