"""Typed environment Capability Graph (CP-004, CP-005).

A ``CapabilityGraph`` is a typed view of what the local environment can actually
do — which test/lint/type tooling, LLM provider, and agent clients are present —
with dependency edges between capabilities (e.g. a strict harness depends on a
test runner). It is built from live detection (``detector.build_capability_graph``)
and read by the resolver, ``doctor``, and capability-aware workflow selection.

Layering (doc 58): this module is L3 (Governance). It imports only ``pydantic``;
it never imports a higher layer (workflows L6, providers gateway L7, Brain L8),
so upper layers consume it via injection, never the reverse.

Distinct from the client ``CapabilityMatrix`` (``configurator/capability.py``),
which models per-agent *features* (mcp/subagents/sampling); this models the typed
*environment* graph with dependency edges (CP-003 vs CP-004).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CAPABILITY_NODE_SCHEMA_VERSION = "opencontext.capability_node.v1"
CAPABILITY_GRAPH_SCHEMA_VERSION = "opencontext.capability_graph.v1"

CapabilityKind = Literal["test", "lint", "type", "provider", "agent", "vcs", "harness"]


class CapabilityNode(BaseModel):
    """A single environment capability with detection evidence and dependencies."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = CAPABILITY_NODE_SCHEMA_VERSION
    id: str = Field(description="Stable capability id, e.g. 'pytest', 'provider.anthropic'.")
    kind: CapabilityKind = Field(description="Capability category.")
    available: bool = Field(description="Whether this capability was detected locally.")
    evidence: str = Field(default="", description="What caused detection (file/source).")
    version: str | None = Field(default=None, description="Detected version, if known.")
    depends_on: list[str] = Field(
        default_factory=list,
        description="Ids of capabilities this one requires to be ready.",
    )


class CapabilityGraph(BaseModel):
    """A graph of ``CapabilityNode``s with dependency-edge readiness queries."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = CAPABILITY_GRAPH_SCHEMA_VERSION
    nodes: list[CapabilityNode] = Field(default_factory=list)

    def get(self, capability_id: str) -> CapabilityNode | None:
        """Return the node for ``capability_id`` or ``None`` when absent."""
        for node in self.nodes:
            if node.id == capability_id:
                return node
        return None

    def is_ready(self, capability_id: str) -> bool:
        """True when the capability is available AND every dependency is ready.

        Cycle-safe: a node already on the resolution stack is treated as not
        ready rather than recursing forever.
        """
        return self._is_ready(capability_id, set())

    def _is_ready(self, capability_id: str, seen: set[str]) -> bool:
        if capability_id in seen:
            return False
        node = self.get(capability_id)
        if node is None or not node.available:
            return False
        seen = seen | {capability_id}
        return all(self._is_ready(dep, seen) for dep in node.depends_on)

    def unmet_dependencies(self, capability_id: str) -> list[str]:
        """Return the declared dependencies of ``capability_id`` that are not ready.

        A dependency that is missing from the graph entirely is also reported as
        unmet. Returns an empty list for an unknown or dependency-free capability.
        """
        node = self.get(capability_id)
        if node is None:
            return []
        return [dep for dep in node.depends_on if not self.is_ready(dep)]

    def available_ids(self) -> set[str]:
        """Return the ids of every capability that is ready (available + deps met).

        This is the set capability-aware workflow selection consumes (CP-011): an
        injected, plain ``set[str]`` rather than the full graph, so the consumer
        (L6 selection) never depends on graph internals.
        """
        return {node.id for node in self.nodes if self.is_ready(node.id)}
