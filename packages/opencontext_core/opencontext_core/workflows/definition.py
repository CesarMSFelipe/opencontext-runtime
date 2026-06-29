"""Declarative workflow definition schema (Workflow Contract v1).

PR-003 turns the scattered, hardcoded workflow declarations (``WORKFLOW_TRACKS``,
``_WORKFLOW_TRACK_ALIASES``, ``PHASE_PERSONAS``, ``OC_NEW_FLOW``) into a single,
versioned, validatable artifact: a graph of nodes and edges with per-node persona,
required harnesses/skills, and phase output contracts.

Layering (doc 58): this module lives in L6 (Registries). It imports only L0
contracts (``compat``) — never Runtime, harness, agents, or config — so the
declarative graph cannot create an upward/circular dependency.

Global IDs (doc 59): a workflow id is a slug (``sdd``, ``oc-flow``); its addressable
global id is ``wf_<slug>`` and a node's is ``node_<slug>``. The bare slugs remain the
registry keys so resolution stays human-readable; the prefixed forms are exposed for
event/receipt addressing.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import StrEnum

# Workflow Contract v1 (doc 59 — internal contract versioning). Bumped on a
# breaking change to the workflow schema; asserted by a guard test.
WORKFLOW_CONTRACT_VERSION = 1

# Serialization schema string carried on every definition (spec WD1).
WORKFLOW_SCHEMA_VERSION = "opencontext.workflow.v1"


def workflow_uid(slug: str) -> str:
    """Return the addressable global workflow id ``wf_<slug>`` (doc 59)."""
    return f"wf_{slug}"


def node_uid(slug: str) -> str:
    """Return the addressable global node id ``node_<slug>`` (doc 59)."""
    return f"node_{slug}"


class WorkflowKind(StrEnum):
    """The kind of workflow. SDD and OC Flow coexist over shared infra (doc §9.2)."""

    SDD = "sdd"
    OC_FLOW = "oc-flow"
    CUSTOM = "custom"


class WorkflowStrategy(StrEnum):
    """Strategy metadata describing how a workflow trades cost for rigor (WR-CONV)."""

    STANDARD = "standard"
    FAST = "fast"
    CHEAP = "cheap"
    CAREFUL = "careful"
    ENTERPRISE = "enterprise"
    RESEARCH = "research"
    LOCAL_FIRST = "local_first"


class CostLevel(StrEnum):
    """Expected aggregate cost of running a workflow (WR-CONV)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskLevel(StrEnum):
    """Expected blast-radius/risk of a workflow (WR-CONV)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WorkflowNodeDefinition(BaseModel):
    """A single node (phase) in a workflow graph.

    Carries the persona/role that drives the node, the skills and harnesses it
    requires, the artifacts it must produce (its output contract), and the gates
    evaluated against it.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Node id (slug), e.g. 'apply'. Unique within a workflow.")
    label: str = Field(description="Human-readable node label.")
    role: str = Field(description="Persona/role id that drives the node, e.g. 'oc-builder'.")
    action: str = Field(description="What the node does, e.g. 'run_phase'.")
    required_personas: list[str] = Field(
        default_factory=list, description="Personas this node may delegate to."
    )
    required_skills: list[str] = Field(
        default_factory=list, description="Skill ids the node requires."
    )
    required_harnesses: list[str] = Field(
        default_factory=list, description="Harness ids the node must run (output gates)."
    )
    required_outputs: list[str] = Field(
        default_factory=list, description="Artifacts the node must produce (output contract)."
    )
    gates: list[str] = Field(default_factory=list, description="Gate ids evaluated for the node.")
    retry_policy: dict[str, Any] = Field(
        default_factory=dict, description="Optional retry policy for the node."
    )

    @property
    def uid(self) -> str:
        """Addressable global node id ``node_<slug>`` (doc 59)."""
        return node_uid(self.id)


class WorkflowEdgeDefinition(BaseModel):
    """A directed edge between two nodes, optionally conditional."""

    model_config = ConfigDict(extra="forbid")

    from_node: str = Field(description="Source node id.")
    to_node: str = Field(description="Target node id.")
    condition: str | None = Field(
        default=None, description="Optional condition gating the transition."
    )


class WorkflowDefinition(BaseModel):
    """A declarative, versioned workflow: a graph of nodes and edges plus metadata.

    Registering a new definition (e.g. OC Flow) requires no Runtime Core change —
    only a call to ``WorkflowRegistry.register`` (spec WR1).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default=WORKFLOW_SCHEMA_VERSION, description="Workflow schema version string."
    )
    id: str = Field(description="Workflow id (slug), e.g. 'sdd'. Registry key.")
    version: str = Field(description="Workflow definition version, e.g. '1'.")
    label: str = Field(description="Human-readable workflow label.")
    kind: str = Field(description="Workflow kind: 'sdd' | 'oc-flow' | 'custom'.")
    start_node: str = Field(description="Id of the entry node.")
    terminal_nodes: list[str] = Field(description="Ids of terminal (end) nodes.")
    nodes: dict[str, WorkflowNodeDefinition] = Field(description="Nodes keyed by node id.")
    edges: list[WorkflowEdgeDefinition] = Field(
        default_factory=list, description="Directed edges between nodes."
    )

    # --- Convergence metadata (WR-CONV) -------------------------------------
    strategy: WorkflowStrategy = Field(
        default=WorkflowStrategy.STANDARD, description="How the workflow trades cost for rigor."
    )
    expected_cost: CostLevel = Field(
        default=CostLevel.MEDIUM, description="Expected aggregate cost."
    )
    risk_level: RiskLevel = Field(default=RiskLevel.MEDIUM, description="Expected blast radius.")
    default_profile: str | None = Field(
        default=None, description="Profile applied when none is requested."
    )
    compatible_profiles: list[str] = Field(
        default_factory=list,
        description="Profiles allowed for this workflow (empty = any allowed).",
    )
    required_capabilities: list[str] = Field(
        default_factory=list, description="Capabilities the workflow needs to run."
    )

    # Phase-subset profiles: profile name -> ordered node ids it executes. Mirrors
    # the legacy WORKFLOW_TRACKS phase sets so resolution parity holds.
    profiles: dict[str, list[str]] = Field(
        default_factory=dict, description="Named phase-subset profiles (name -> node ids)."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Free-form metadata (e.g. shared-infra seams)."
    )

    @property
    def uid(self) -> str:
        """Addressable global workflow id ``wf_<slug>`` (doc 59)."""
        return workflow_uid(self.id)

    def incoming(self, node_id: str) -> list[str]:
        """Return the source nodes of every edge pointing at ``node_id``."""
        return [e.from_node for e in self.edges if e.to_node == node_id]

    def phase_order(self, profile: str | None = None) -> list[str]:
        """Return the topological execution order of the node ids for ``profile``.

        When ``profile`` names a registered phase-subset profile, only those nodes
        are scheduled; otherwise all nodes participate (declared order). Ordering
        uses the same drop-unsatisfiable Kahn pass as the legacy
        ``HarnessRunner.resolve_dag`` so a registry-resolved order is identical to
        the legacy scheduler's (spec BAK1).
        """
        if profile is not None and profile in self.profiles:
            subset = list(self.profiles[profile])
        else:
            subset = list(self.nodes.keys())
        subset_set = set(subset)
        # In-subset dependency map derived from edges (out-of-subset deps dropped).
        deps = {n: [d for d in self.incoming(n) if d in subset_set] for n in subset}
        return _topo_order(subset, deps)


def _topo_order(phases: list[str], deps: dict[str, list[str]]) -> list[str]:
    """Topologically order ``phases`` by ``deps`` (Kahn, drop-unsatisfiable).

    Ready phases are emitted in their declared ``phases`` order; a phase whose
    in-set dependencies can never all be satisfied is dropped rather than run out
    of order. Reimplemented locally (not imported from ``harness``) to keep the L6
    workflows package free of any upward dependency on the runner (doc 58).
    """
    completed: set[str] = set()
    ordered: list[str] = []
    progressed = True
    while progressed:
        progressed = False
        for phase in phases:
            if phase in completed:
                continue
            if set(deps.get(phase, [])) <= completed:
                ordered.append(phase)
                completed.add(phase)
                progressed = True
    return ordered
