"""Configurable workflow engine."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from time import perf_counter
from uuid import uuid4

from opencontext_core.compat import UTC
from opencontext_core.config import OpenContextConfig
from opencontext_core.errors import ConfigurationError
from opencontext_core.models.workflow import WorkflowRunState, WorkflowStepResult
from opencontext_core.workflow.hooks import ContextEngineHooks
from opencontext_core.workflow.steps import (
    WorkflowServices,
    context_apply,
    context_archive,
    context_compress,
    context_explore,
    context_pack,
    context_propose,
    context_rank,
    context_review,
    context_test,
    context_up_code,
    context_verify,
    embeddings_generate,
    llm_generate,
    project_load_manifest,
    project_retrieve,
    prompt_assemble,
    trace_persist,
    trace_sdd_persist,
)

WorkflowStep = Callable[[WorkflowRunState, WorkflowServices], str]


class WorkflowEngine:
    """Executes named YAML workflows through an explicit step registry."""

    def __init__(
        self,
        config: OpenContextConfig,
        services: WorkflowServices,
        registry: dict[str, WorkflowStep] | None = None,
        hooks: ContextEngineHooks | None = None,
    ) -> None:
        self.config = config
        self.services = services
        self.registry = registry or default_step_registry()
        self.hooks = hooks or ContextEngineHooks()

    def run_workflow(
        self,
        state: WorkflowRunState,
        workflow_config: object,
    ) -> WorkflowRunState:
        """Execute a workflow config against an existing state.

        Supports string steps (backward compat), and structured step dicts:
        - {"type": "parallel", "steps": [...]} — run child steps sequentially (all must pass)
        - {"type": "if", "condition": callable, "then": [...], "else": [...]} — conditional
        - {"type": "fan-out", "step": "name", "inputs": [...]} — repeat step per input
        Resume is supported via state.metadata["step_index"].
        """
        steps = list(getattr(workflow_config, "steps", []))
        step_index = state.metadata.get("step_index", 0)

        for i, step_def in enumerate(steps):
            if i < step_index:
                continue
            self._execute_step_def(state, step_def)
            state.metadata["step_index"] = i + 1

        return state

    def _execute_step_def(self, state: WorkflowRunState, step_def: object) -> None:
        """Dispatch a single step definition (string or dict)."""
        if isinstance(step_def, str):
            self._run_named_step(state, step_def)
            return

        step_type = step_def.get("type") if isinstance(step_def, dict) else getattr(step_def, "type", None)  # type: ignore[union-attr]

        if step_type == "parallel":
            child_steps = (
                step_def.get("steps", [])
                if isinstance(step_def, dict)
                else (getattr(step_def, "steps", None) or [])
            )
            for child in child_steps:
                self._run_named_step(state, child)

        elif step_type == "if":
            condition = (
                step_def.get("condition")
                if isinstance(step_def, dict)
                else getattr(step_def, "condition", None)
            )
            then_steps = (
                step_def.get("then", [])
                if isinstance(step_def, dict)
                else (getattr(step_def, "then", None) or [])
            )
            else_steps = (
                step_def.get("else", [])
                if isinstance(step_def, dict)
                else (getattr(step_def, "else_", None) or [])
            )
            branch = then_steps if (callable(condition) and condition(state)) else else_steps
            for child in branch:
                self._run_named_step(state, child)

        elif step_type == "fan-out":
            fan_step = (
                step_def.get("step")
                if isinstance(step_def, dict)
                else getattr(step_def, "step", None)
            )
            inputs = (
                step_def.get("inputs", [])
                if isinstance(step_def, dict)
                else (getattr(step_def, "inputs", None) or [])
            )
            for inp in inputs:
                state.metadata["current_input"] = inp
                self._run_named_step(state, fan_step)

        else:
            step_name = (
                step_def.get("step")
                if isinstance(step_def, dict)
                else getattr(step_def, "step", None)
            )
            if step_name:
                self._run_named_step(state, step_name)

    def _run_named_step(self, state: WorkflowRunState, step_name: str) -> str:
        """Look up and execute a named step from the registry."""
        step = self.registry.get(step_name)
        if step is None:
            raise ConfigurationError(f"Unknown workflow step: {step_name}")
        step_start = datetime.now(tz=UTC)
        started = perf_counter()
        summary = step(state, self.services)
        duration_ms = (perf_counter() - started) * 1000
        step_end = datetime.now(tz=UTC)
        state.step_results.append(
            WorkflowStepResult(
                name=step_name,
                duration_ms=duration_ms,
                summary=summary,
                start_time=step_start,
                end_time=step_end,
            )
        )
        return summary

    def run(self, workflow_name: str, user_request: str) -> WorkflowRunState:
        """Execute a named workflow."""

        workflow = self.config.workflows.get(workflow_name)
        if workflow is None:
            raise ConfigurationError(f"Unknown workflow: {workflow_name}")
        state = WorkflowRunState(
            run_id=str(uuid4()),
            workflow_name=workflow_name,
            user_request=user_request,
        )
        if self.hooks.before_run is not None:
            self.hooks.before_run(state)
        for step_name in workflow.steps:
            self._run_named_step(state, step_name)
        if self.hooks.after_run is not None:
            self.hooks.after_run(state)
        return state


def default_step_registry() -> dict[str, WorkflowStep]:
    """Return the built-in workflow step registry."""

    return {
        # Core workflow steps
        "project.load_manifest": project_load_manifest,
        "project.retrieve": project_retrieve,
        "context.rank": context_rank,
        "context.pack": context_pack,
        "context.compress": context_compress,
        "prompt.assemble": prompt_assemble,
        "llm.generate": llm_generate,
        "trace.persist": trace_persist,
        # SDD-style workflow steps
        "context.explore": context_explore,
        "context.propose": context_propose,
        "context.apply": context_apply,
        "context.test": context_test,
        "context.verify": context_verify,
        "context.review": context_review,
        "context.archive": context_archive,
        "context.up-code": context_up_code,
        "trace.sdd_persist": trace_sdd_persist,
        # Embedding generation
        "embeddings.generate": embeddings_generate,
    }
