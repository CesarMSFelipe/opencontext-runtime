"""Declarative workflow layer (PR-003 Workflow Registry, L6).

Exposes the Workflow Contract v1: a versioned :class:`WorkflowDefinition` graph, a
:class:`WorkflowRegistry`, a :class:`WorkflowResolver` (which supersedes the legacy
alias table behind the ``runtime.registry_enabled`` flag), graph validation, and an
inspectable selection policy. Execution still delegates to the existing
``HarnessRunner`` (spec INT1).
"""

from __future__ import annotations

from opencontext_core.workflows.aliases import (
    WORKFLOW_ALIASES,
    UnknownWorkflowAlias,
    is_alias,
    resolve_alias,
)
from opencontext_core.workflows.capability_selection import CapabilityAwareSelection
from opencontext_core.workflows.definition import (
    WORKFLOW_CONTRACT_VERSION,
    WORKFLOW_SCHEMA_VERSION,
    CostLevel,
    RiskLevel,
    WorkflowDefinition,
    WorkflowEdgeDefinition,
    WorkflowKind,
    WorkflowNodeDefinition,
    WorkflowStrategy,
    node_uid,
    workflow_uid,
)
from opencontext_core.workflows.registry import (
    WorkflowNotFound,
    WorkflowRegistry,
    definition_from_dict,
    load_definition_from_yaml,
)
from opencontext_core.workflows.resolver import (
    WORKFLOW_SELECTION_SCHEMA_VERSION,
    ResolvedWorkflow,
    WorkflowResolutionError,
    WorkflowResolver,
    WorkflowSelectionReceipt,
)
from opencontext_core.workflows.selection import SelectionDecision, SelectionPolicy
from opencontext_core.workflows.validation import (
    CoexistenceReport,
    WorkflowCapabilityError,
    WorkflowProfileError,
    WorkflowValidationError,
    missing_capabilities,
    validate,
    validate_coexistence,
    validate_profile,
)

__all__ = [
    "WORKFLOW_ALIASES",
    "WORKFLOW_CONTRACT_VERSION",
    "WORKFLOW_SCHEMA_VERSION",
    "WORKFLOW_SELECTION_SCHEMA_VERSION",
    "CapabilityAwareSelection",
    "CoexistenceReport",
    "CostLevel",
    "ResolvedWorkflow",
    "RiskLevel",
    "SelectionDecision",
    "SelectionPolicy",
    "UnknownWorkflowAlias",
    "WorkflowCapabilityError",
    "WorkflowDefinition",
    "WorkflowEdgeDefinition",
    "WorkflowKind",
    "WorkflowNodeDefinition",
    "WorkflowNotFound",
    "WorkflowProfileError",
    "WorkflowRegistry",
    "WorkflowResolutionError",
    "WorkflowResolver",
    "WorkflowSelectionReceipt",
    "WorkflowStrategy",
    "WorkflowValidationError",
    "definition_from_dict",
    "is_alias",
    "load_definition_from_yaml",
    "missing_capabilities",
    "node_uid",
    "resolve_alias",
    "validate",
    "validate_coexistence",
    "validate_profile",
    "workflow_uid",
]
