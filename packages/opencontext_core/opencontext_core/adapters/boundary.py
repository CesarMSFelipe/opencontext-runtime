"""Adapter boundary models and service for external coding surface integration.

The boundary layer translates between external coding tool requests and
internal OpenContext harness workflows. It enables:
- CI/CD integration (codex, opencode)
- IDE plugin requests (cursor, claude_code, windsurf, openclaw)
- Provider-neutral dispatch to appropriate adapters
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import StrEnum


class AdapterTarget(StrEnum):
    """Supported integration targets at the boundary layer."""

    CODEX = "codex"
    CURSOR = "cursor"
    CLAUDE_CODE = "claude_code"
    WINDSURF = "windsurf"
    OPENCODE = "opencode"
    OPENCLAW = "openclaw"


class AdapterRequest(BaseModel):
    """Inbound request from an adapter to OpenContext."""

    model_config = ConfigDict(extra="forbid")

    target: AdapterTarget = Field(description="Caller adapter target.")
    task: str = Field(description="Task or question for context operations.")
    workflow_pack: str | None = Field(default=None, description="Optional workflow pack name.")
    root: str = Field(default=".", description="Project root directory.")
    budget_mode: str = Field(default="warn", description="Budget enforcement mode.")


@dataclass
class BoundaryResult:
    """Result from a boundary service dispatch."""

    success: bool
    target: str
    run_id: str | None = None
    message: str = ""
    phases: list[dict[str, Any]] = field(default_factory=list)
    gates: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class BoundaryService:
    """Service that dispatches AdapterRequests to the appropriate handler.

    Provider-neutral dispatch: translates external coding tool requests
    into internal harness workflow executions or adapter invocations.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd()

    def dispatch(self, request: AdapterRequest) -> BoundaryResult:
        """Dispatch an adapter request to the appropriate handler.

        The dispatch strategy is:
        - SDD workflow requests (workflow_pack is set) → HarnessRunner
        - Direct execution requests → appropriate AgentAdapter
        - Diagnostic/info requests → inline handler
        """
        if request.workflow_pack:
            return self._run_workflow(request)

        if request.target == AdapterTarget.OPENCODE.value:
            return self._handle_opencode(request)

        return self._generic_dispatch(request)

    def _run_workflow(self, request: AdapterRequest) -> BoundaryResult:
        """Run a harness workflow in response to an adapter request."""
        from opencontext_core.harness.models import BudgetMode
        from opencontext_core.harness.runner import HarnessRunner

        try:
            root = Path(request.root).resolve()
            budget = (
                BudgetMode.STRICT
                if request.budget_mode == "strict"
                else BudgetMode.WARN
                if request.budget_mode == "warn"
                else BudgetMode.OFF
            )
            runner = HarnessRunner(root=root)
            result = runner.run(
                workflow=request.workflow_pack or "sdd",
                task=request.task,
                budget_mode=budget,
            )

            return BoundaryResult(
                success=result.status not in ("failed", "error"),
                target=request.target,
                run_id=result.run_id,
                message=f"Workflow completed: {result.status}",
                phases=[
                    {
                        "phase": ledger.phase,
                        "status": (
                            ledger.status.value
                            if hasattr(ledger.status, "value")
                            else str(ledger.status)
                        ),
                    }
                    for ledger in result.ledgers
                ],
                gates=[
                    {
                        "id": g.id,
                        "phase": g.phase,
                        "status": g.status if hasattr(g.status, "value") else str(g.status),
                    }
                    for g in result.gates
                ],
                warnings=result.warnings,
                metadata={
                    "workflow": result.workflow,
                    "task": result.task,
                    "final_status": (
                        result.status.value
                        if hasattr(result.status, "value")
                        else str(result.status)
                    ),
                    "total_ledgers": len(result.ledgers),
                    "total_gates": len(result.gates),
                },
            )
        except Exception as exc:
            return BoundaryResult(
                success=False,
                target=request.target,
                error=f"Workflow execution failed: {exc}",
            )

    def _handle_opencode(self, request: AdapterRequest) -> BoundaryResult:
        """Handle OpenCode-specific requests inline.

        OpenCode integration executes SDD workflows directly through
        the harness runner with no external adapter.
        """
        req = AdapterRequest(
            target=request.target,
            task=request.task,
            workflow_pack=request.workflow_pack or "sdd",
            root=request.root,
            budget_mode=request.budget_mode,
        )
        return self._run_workflow(req)

    def _generic_dispatch(self, request: AdapterRequest) -> BoundaryResult:
        """Generic dispatch for targets without specific handling.

        Uses LocalAdapter to run basic commands or returns a structured
        response explaining how to set up integration.
        """
        from opencontext_core.adapters.local import LocalAdapter

        adapter = LocalAdapter()
        if not adapter.check_available():
            return BoundaryResult(
                success=True,
                target=request.target,
                message=(
                    f"Adapter '{request.target}' received. "
                    f"Run 'opencontext init' to configure integration."
                ),
                metadata={"hint": "run `opencontext init` to configure"},
            )

        agent_result = adapter.execute(
            instruction=request.task,
            cwd=self.root,
            timeout=30,
        )
        return BoundaryResult(
            success=agent_result.success,
            target=request.target,
            message=(
                "Command executed successfully"
                if agent_result.success
                else f"Command failed: {agent_result.stderr[:500]}"
            ),
            metadata={
                "exit_code": agent_result.exit_code,
                "stdout_preview": agent_result.stdout[:500],
            },
            error=agent_result.stderr if not agent_result.success else None,
        )
