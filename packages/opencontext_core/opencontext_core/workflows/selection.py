"""Inspectable workflow-selection policy seam (WR-CONV, OC-FINAL-CONVERGENCE-001 §6).

Given an intent, a profile, and the available capabilities, the policy recommends a
workflow id with a recorded reason. The default recommendation is the explicit
request; selection is never hidden — every decision carries a reason and feeds a
later ``workflow explain``. The policy degrades or denies gracefully when a required
capability is missing.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.workflows.registry import WorkflowRegistry
from opencontext_core.workflows.validation import missing_capabilities


class SelectionDecision(BaseModel):
    """The result of a workflow-selection policy run (inspectable, reasoned)."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(description="Recommended workflow id.")
    profile: str = Field(description="Recommended profile.")
    reason: str = Field(description="Why this workflow/profile was recommended.")
    degraded: bool = Field(
        default=False,
        description="True when the recommendation runs without a required capability.",
    )
    denied: bool = Field(
        default=False, description="True when no workflow can run with the available capabilities."
    )
    missing_capabilities: list[str] = Field(
        default_factory=list, description="Required capabilities that are unavailable."
    )
    candidates: list[str] = Field(
        default_factory=list, description="Workflow ids considered during selection."
    )


class SelectionPolicy:
    """Recommends a workflow given an intent/profile/capabilities (WR-CONV)."""

    def __init__(self, registry: WorkflowRegistry) -> None:
        self._registry = registry

    def select(
        self,
        *,
        intent: str,
        profile: str,
        capabilities: set[str],
        requested: str | None = None,
    ) -> SelectionDecision:
        """Recommend a workflow id with a recorded reason.

        The default recommendation is the explicit ``requested`` workflow. When the
        requested workflow needs a capability the environment lacks, the decision is
        marked ``degraded`` with an actionable reason (deprioritised, not silently
        switched). When nothing is requested, the first capability-satisfied
        workflow is recommended; if none qualifies the decision is ``denied``.
        """
        candidates = self._registry.list_ids()

        if requested is not None and self._registry.has(requested):
            defn = self._registry.get(requested)
            missing = missing_capabilities(defn, capabilities)
            if missing:
                return SelectionDecision(
                    workflow_id=requested,
                    profile=profile,
                    reason=(
                        f"requested {requested!r} for intent {intent!r} is missing "
                        f"capabilities {missing}; install them or pick a lighter workflow"
                    ),
                    degraded=True,
                    missing_capabilities=missing,
                    candidates=candidates,
                )
            return SelectionDecision(
                workflow_id=requested,
                profile=profile,
                reason=f"explicit request {requested!r} honored for intent {intent!r}",
                candidates=candidates,
            )

        # No explicit request: pick the first workflow whose capabilities are met.
        for workflow_id in candidates:
            defn = self._registry.get(workflow_id)
            if not missing_capabilities(defn, capabilities):
                return SelectionDecision(
                    workflow_id=workflow_id,
                    profile=profile or (defn.default_profile or ""),
                    reason=(
                        f"selected {workflow_id!r} for intent {intent!r}: "
                        "first workflow with all required capabilities available"
                    ),
                    candidates=candidates,
                )

        return SelectionDecision(
            workflow_id="",
            profile=profile,
            reason=(f"no workflow satisfies the available capabilities for intent {intent!r}"),
            denied=True,
            candidates=candidates,
        )
