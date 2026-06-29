"""Workflow resolver (spec RES1) and workflow-selection receipt (spec RCPT1).

The resolver turns a requested workflow name (including legacy aliases) into a
registered :class:`WorkflowDefinition`, a profile, and the resolved phase order —
before phase scheduling begins. It produces an auditable selection receipt but does
not execute anything: execution stays with the existing ``HarnessRunner`` (spec
INT1).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC
from opencontext_core.workflows.aliases import is_alias, resolve_alias
from opencontext_core.workflows.definition import WorkflowDefinition
from opencontext_core.workflows.registry import WorkflowNotFound, WorkflowRegistry
from opencontext_core.workflows.validation import validate_profile

WORKFLOW_SELECTION_SCHEMA_VERSION = "opencontext.workflow_selection.v1"


class WorkflowResolutionError(ValueError):
    """Raised when a requested workflow name cannot be resolved."""


class ResolvedWorkflow(BaseModel):
    """The outcome of resolving a workflow name (definition + profile + order)."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    requested: str = Field(description="The workflow name the caller requested.")
    definition: WorkflowDefinition = Field(description="The resolved definition.")
    profile: str = Field(description="The resolved phase-subset/compat profile.")
    alias_used: str | None = Field(
        default=None, description="The legacy alias that was resolved, if any."
    )
    reason: str = Field(description="Why this workflow/profile was selected.")
    phase_order: list[str] = Field(description="The resolved phase execution order.")


class WorkflowSelectionReceipt(BaseModel):
    """Auditable record of a workflow selection (spec RCPT1)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = WORKFLOW_SELECTION_SCHEMA_VERSION
    requested: str = Field(description="Requested workflow name.")
    resolved: str = Field(description="Resolved workflow id.")
    workflow_uid: str = Field(description="Addressable workflow id (wf_<slug>).")
    profile: str = Field(description="Resolved profile.")
    reason: str = Field(description="Selection reason.")
    alias_used: str | None = Field(default=None, description="Legacy alias used, if any.")
    phase_order: list[str] = Field(default_factory=list, description="Resolved phase order.")
    strategy: str = Field(description="Workflow strategy metadata.")
    expected_cost: str = Field(description="Workflow expected-cost metadata.")
    risk_level: str = Field(description="Workflow risk-level metadata.")
    selected_at: str = Field(
        default_factory=lambda: datetime.now(tz=UTC).isoformat(),
        description="UTC timestamp of the selection.",
    )


class WorkflowResolver:
    """Resolves a requested workflow name to a definition + profile (spec RES1)."""

    def __init__(self, registry: WorkflowRegistry) -> None:
        self._registry = registry

    def resolve(self, name: str, profile: str | None = None) -> ResolvedWorkflow:
        """Resolve ``name`` (alias or direct id) to a :class:`ResolvedWorkflow`.

        Raises :class:`WorkflowResolutionError` for an unknown name and
        ``WorkflowProfileError`` for an incompatible profile (WR-CONV).
        """
        if is_alias(name):
            workflow_id, alias_profile = resolve_alias(name)
            alias_used: str | None = name
            reason = f"legacy alias {name!r} -> {workflow_id}/{alias_profile}"
            default_profile = alias_profile
        else:
            workflow_id = name
            alias_used = None
            reason = f"direct workflow id {name!r}"
            default_profile = None

        try:
            definition = self._registry.get(workflow_id)
        except WorkflowNotFound as exc:
            raise WorkflowResolutionError(str(exc)) from exc

        effective_profile = profile or default_profile or definition.default_profile
        if effective_profile is None:
            raise WorkflowResolutionError(
                f"workflow {workflow_id!r} has no profile and none was requested"
            )

        validate_profile(definition, effective_profile)
        order = definition.phase_order(effective_profile)

        return ResolvedWorkflow(
            requested=name,
            definition=definition,
            profile=effective_profile,
            alias_used=alias_used,
            reason=reason,
            phase_order=order,
        )

    @staticmethod
    def build_receipt(resolved: ResolvedWorkflow) -> WorkflowSelectionReceipt:
        """Build the workflow-selection receipt for a resolution (spec RCPT1)."""
        defn = resolved.definition
        return WorkflowSelectionReceipt(
            requested=resolved.requested,
            resolved=defn.id,
            workflow_uid=defn.uid,
            profile=resolved.profile,
            reason=resolved.reason,
            alias_used=resolved.alias_used,
            phase_order=list(resolved.phase_order),
            strategy=str(defn.strategy),
            expected_cost=str(defn.expected_cost),
            risk_level=str(defn.risk_level),
        )
