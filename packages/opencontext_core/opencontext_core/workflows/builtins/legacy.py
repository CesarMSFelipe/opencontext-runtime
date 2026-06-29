"""Built-in backing definition for the legacy quality tracks (WR2 / BAK1 parity).

The legacy ``HarnessRunner`` scheduled tracks beyond the SDD phase-subset profiles:
``full+judgment`` / ``full+gga`` / ``full+quality`` layer an adversarial-review
(``judgment``) and/or quality-gate (``gga``) phase on top of the full SDD order
(see ``agents.sdd_orchestrator.WORKFLOW_TRACKS``). Those two phases are not part of
the SDD graph (``builtins/sdd.yaml`` mirrors ``PHASE_ORDER`` exactly, asserted by the
SDD1 parity tests), so they cannot be expressed as SDD profiles.

This module declares a single ``sdd-quality`` definition — the SDD graph plus the
``judgment`` and ``gga`` nodes — with one profile per quality track. The alias table
(:mod:`opencontext_core.workflows.aliases`) maps each legacy track name onto this
definition + its profile, so the registry resolves every known legacy track cleanly
and ``workflow.validation.failed`` stays reserved for genuinely unknown workflows
(vNext registry parity, spec VDM-004).

The SDD nodes and edges are reused from the loaded SDD definition (single source of
truth) so this never drifts from ``builtins/sdd.yaml``. The two added phases use the
``oc-reviewer`` persona, which already drives code review, GGA gates, and judgment-day
review.
"""

from __future__ import annotations

from opencontext_core.workflows.definition import (
    WorkflowDefinition,
    WorkflowEdgeDefinition,
    WorkflowNodeDefinition,
)

# Registry id of the backing definition for the legacy quality tracks.
SDD_QUALITY_ID = "sdd-quality"

# Profile names (== legacy track names) this definition exposes.
PROFILE_FULL_JUDGMENT = "full+judgment"
PROFILE_FULL_GGA = "full+gga"
PROFILE_FULL_QUALITY = "full+quality"

_JUDGMENT_NODE = WorkflowNodeDefinition(
    id="judgment",
    label="Judgment",
    role="oc-reviewer",
    action="run_phase",
)
_GGA_NODE = WorkflowNodeDefinition(
    id="gga",
    label="GGA Quality Gate",
    role="oc-reviewer",
    action="run_phase",
)


def build_sdd_quality(sdd: WorkflowDefinition) -> WorkflowDefinition:
    """Build the ``sdd-quality`` definition from the loaded SDD definition.

    Reuses every SDD node/edge verbatim (so persona/output contracts cannot drift
    from ``sdd.yaml``) and adds the ``gga`` and ``judgment`` phases gated on
    ``verify``. The per-track profiles reproduce the legacy
    ``WORKFLOW_TRACKS`` phase orders for ``full+judgment`` / ``full+gga`` /
    ``full+quality`` (spec BAK1).
    """
    base_order = list(sdd.nodes.keys())  # == PHASE_ORDER (SDD1 parity)
    nodes = {node_id: sdd.nodes[node_id] for node_id in base_order}
    nodes[_GGA_NODE.id] = _GGA_NODE
    nodes[_JUDGMENT_NODE.id] = _JUDGMENT_NODE

    # SDD edges verbatim + the quality-track wiring: both gga and judgment hang off
    # verify; full+quality additionally orders judgment after gga. In-subset edge
    # filtering (WorkflowDefinition.phase_order) drops the out-of-subset deps per
    # profile, so each profile's topological order matches its legacy track exactly.
    edges = list(sdd.edges)
    edges.append(WorkflowEdgeDefinition(from_node="verify", to_node=_GGA_NODE.id))
    edges.append(WorkflowEdgeDefinition(from_node="verify", to_node=_JUDGMENT_NODE.id))
    edges.append(WorkflowEdgeDefinition(from_node=_GGA_NODE.id, to_node=_JUDGMENT_NODE.id))

    profiles = {
        PROFILE_FULL_JUDGMENT: [*base_order, _JUDGMENT_NODE.id],
        PROFILE_FULL_GGA: [*base_order, _GGA_NODE.id],
        PROFILE_FULL_QUALITY: [*base_order, _GGA_NODE.id, _JUDGMENT_NODE.id],
    }

    return WorkflowDefinition(
        id=SDD_QUALITY_ID,
        version=sdd.version,
        label="Spec-Driven Development (quality tracks)",
        kind="sdd",
        start_node=sdd.start_node,
        terminal_nodes=[*sdd.terminal_nodes, _GGA_NODE.id, _JUDGMENT_NODE.id],
        nodes=nodes,
        edges=edges,
        strategy=sdd.strategy,
        expected_cost=sdd.expected_cost,
        risk_level=sdd.risk_level,
        default_profile=PROFILE_FULL_QUALITY,
        compatible_profiles=[
            PROFILE_FULL_JUDGMENT,
            PROFILE_FULL_GGA,
            PROFILE_FULL_QUALITY,
        ],
        profiles=profiles,
        metadata=dict(sdd.metadata),
    )
