"""OC Flow — the fast, local-first operational workflow (PR-007, book doc 04).

OC Flow is the first-run engineering workflow for localized tasks (failing tests,
small bugfixes, lint/type errors, small refactors). It is a declarative 8-node
:class:`~opencontext_core.workflows.definition.WorkflowDefinition` executed by
:class:`OCFlowRunner` under shared Runtime governance, coexisting with SDD over the
same registries, stores, personas, skills, harnesses, events and receipts.

Flag-gated by ``runtime.oc_flow_enabled`` (default off) so the branch always runs.
"""

from __future__ import annotations

from opencontext_core.oc_flow.budgets import (
    OC_FLOW_BUDGETS,
    OC_FLOW_TOTAL_CEILING,
    OC_FLOW_TOTAL_WARN,
    BudgetGuard,
    LaneConfig,
    lane_config,
    resolve_max_attempts,
)
from opencontext_core.oc_flow.definition import (
    OC_FLOW_ID,
    oc_flow_definition,
    oc_flow_registry,
    register_oc_flow,
    resolve_next_node,
)
from opencontext_core.oc_flow.models import (
    OC_FLOW_CONTRACT_VERSION,
    ContextEnvelope,
    DiagnosisAttempt,
    EscalationReport,
    Hypothesis,
    InspectionReport,
    Lane,
    NodeOutcome,
    TaskContract,
)
from opencontext_core.oc_flow.personas import (
    OC_FLOW_NODE_PERSONAS,
    persona_for_oc_flow_node,
    persona_id_for_oc_flow_node,
)
from opencontext_core.oc_flow.runner import (
    OCFlowRunner,
    OCFlowRunResult,
    ResumedRun,
    select_workflow,
    should_escalate_to_sdd,
)
from opencontext_core.oc_flow.skills import (
    OC_FLOW_DEFAULT_BUNDLE,
    oc_flow_skill_registry,
    skills_for_node,
)

__all__ = [
    "OC_FLOW_BUDGETS",
    "OC_FLOW_CONTRACT_VERSION",
    "OC_FLOW_DEFAULT_BUNDLE",
    "OC_FLOW_ID",
    "OC_FLOW_NODE_PERSONAS",
    "OC_FLOW_TOTAL_CEILING",
    "OC_FLOW_TOTAL_WARN",
    "BudgetGuard",
    "ContextEnvelope",
    "DiagnosisAttempt",
    "EscalationReport",
    "Hypothesis",
    "InspectionReport",
    "Lane",
    "LaneConfig",
    "NodeOutcome",
    "OCFlowRunResult",
    "OCFlowRunner",
    "ResumedRun",
    "TaskContract",
    "lane_config",
    "oc_flow_definition",
    "oc_flow_registry",
    "oc_flow_skill_registry",
    "persona_for_oc_flow_node",
    "persona_id_for_oc_flow_node",
    "register_oc_flow",
    "resolve_max_attempts",
    "resolve_next_node",
    "select_workflow",
    "should_escalate_to_sdd",
    "skills_for_node",
]
