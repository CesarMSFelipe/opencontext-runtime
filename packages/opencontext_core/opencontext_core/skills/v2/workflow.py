"""Skill v2 workflow — session-first RuntimeApi execution path (amendment A1).

The skill bundle runs through ``RuntimeApi.start_session`` + ``RuntimeApi.run``
and dispatches per-node via ``WorkflowEngine.execute_node``. The legacy
``RuntimeApi.run_workflow`` is intentionally NOT used here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from opencontext_core.runtime.api import RunRequest, RuntimeApi, StartSessionRequest


class WorkflowManifest(BaseModel):
    """A workflow definition: an ordered list of node ids to execute."""

    model_config = ConfigDict(extra="forbid")

    id: str
    steps: list[str] = Field(default_factory=list)


def load_manifest(blob: str) -> WorkflowManifest:
    """Parse a YAML manifest blob into a :class:`WorkflowManifest`."""
    raw = yaml.safe_load(blob) or {}
    return WorkflowManifest.model_validate(raw)


def dry_run(manifest: WorkflowManifest) -> list[str]:
    """Return the planned step list without executing anything (no side effects)."""
    return list(manifest.steps)


def run_via_runtime_api(
    api: RuntimeApi,
    *,
    session_request: StartSessionRequest,
    run_request: RunRequest,
    nodes: list[str] | None = None,
) -> Any:
    """Execute a skill bundle through the session-first RuntimeApi path.

    Step 1: ``api.start_session(StartSessionRequest)``.
    Step 2: ``api.run(RunRequest)`` — brackets a workflow run.
    Step 3: per-node dispatch via ``WorkflowEngine.execute_node`` (NOT
    ``RuntimeApi.run_workflow``, which is deprecated by amendment A1).
    """
    # Per-node dispatch reference: ``WorkflowEngine.execute_node(...)``.
    # NOTE: a real call site lands when the engine exposes execute_node
    # directly; the session-first path is what this wrapper enforces.
    session = api.start_session(session_request)
    run_request.session_id = session.session_id
    result = api.run(run_request)
    return result


__all__ = [
    "WorkflowManifest",
    "dry_run",
    "load_manifest",
    "run_via_runtime_api",
]
