"""OC Flow workflow definition + edge resolution (PR-007, FLOW-1, FLOW-2).

OC Flow is declared once as YAML (``workflows/builtins/oc_flow.yaml``) and loaded
through the PR-003 :class:`WorkflowRegistry` — registering it requires no Runtime
change (book §30, spec WR1). This module is the integration point: it returns the
validated :class:`WorkflowDefinition`, registers it into a registry, and resolves
the conditional edge graph (book §6) against a node outcome.

Layering (doc 58): OC Flow is L9; this imports only the L6 workflows package and the
L9 OC Flow models — never Runtime upward.
"""

from __future__ import annotations

from functools import lru_cache

from opencontext_core.oc_flow.models import NodeOutcome
from opencontext_core.workflows.builtins import builtins_dir
from opencontext_core.workflows.definition import WorkflowDefinition
from opencontext_core.workflows.registry import (
    WorkflowRegistry,
    load_definition_from_yaml,
)

OC_FLOW_ID = "oc-flow"

# Maps each declarative edge condition (book §6) to the node outcome that satisfies
# it. Unconditional edges (condition ``None``) always apply.
_CONDITION_TO_OUTCOME: dict[str, str] = {
    "inspection_passed": NodeOutcome.PASSED.value,
    "inspection_failed_recoverable": NodeOutcome.FAILED_RECOVERABLE.value,
    "inspection_failed_blocking": NodeOutcome.FAILED_BLOCKING.value,
    "fix_ready": NodeOutcome.FIX_READY.value,
    "needs_context": NodeOutcome.NEEDS_CONTEXT.value,
    "attempts_exhausted": NodeOutcome.ATTEMPTS_EXHAUSTED.value,
}


def _oc_flow_yaml_path() -> str:
    return str(builtins_dir() / "oc_flow.yaml")


@lru_cache(maxsize=1)
def oc_flow_definition() -> WorkflowDefinition:
    """Return the validated 8-node OC Flow :class:`WorkflowDefinition` (FLOW-1).

    Loaded + validated from the built-in YAML; cached because the definition is
    immutable for the process lifetime.
    """
    return load_definition_from_yaml(_oc_flow_yaml_path())


def register_oc_flow(registry: WorkflowRegistry) -> WorkflowDefinition:
    """Register OC Flow into ``registry`` (idempotent) and return the definition."""
    definition = oc_flow_definition()
    if not registry.has(OC_FLOW_ID):
        registry.register(definition)
    return definition


def oc_flow_registry() -> WorkflowRegistry:
    """Return a registry pre-loaded with the built-ins plus OC Flow.

    The product resolution surface: SDD (built-in) and OC Flow coexist in one
    registry, so ``--workflow auto`` and ``--workflow oc-flow`` both resolve here.
    """
    registry = WorkflowRegistry.with_builtins()
    register_oc_flow(registry)
    return registry


def resolve_next_node(
    definition: WorkflowDefinition,
    current_node: str,
    outcome: str | NodeOutcome | None = None,
) -> str | None:
    """Resolve the next node from ``current_node`` given an ``outcome`` (FLOW-2).

    Conditional edges are matched against the outcome via
    :data:`_CONDITION_TO_OUTCOME`; an unconditional edge is the linear successor.
    Returns ``None`` for a terminal node or when no edge matches the outcome.
    """
    outcome_value = outcome.value if isinstance(outcome, NodeOutcome) else outcome
    out_edges = [e for e in definition.edges if e.from_node == current_node]

    # Unconditional successor (linear node) — exactly one, no condition.
    unconditional = [e for e in out_edges if e.condition is None]
    conditional = [e for e in out_edges if e.condition is not None]

    if conditional and outcome_value is not None:
        for edge in conditional:
            wanted = _CONDITION_TO_OUTCOME.get(edge.condition or "")
            if wanted is not None and wanted == outcome_value:
                return edge.to_node

    if unconditional:
        return unconditional[0].to_node

    return None
