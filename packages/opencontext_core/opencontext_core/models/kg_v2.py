"""KG v2 typed/temporal/evidence schema (PR-008, OC-KG-001 §6-11).

Additive Pydantic models layered ON TOP of the existing SQLite graph store. The
SQLite ``Node``/``Edge`` dataclasses (``indexing/graph_db.py``) stay authoritative
for structure and the hot insert path; these models carry the *semantic* layer the
architecture book specifies — typed kinds, temporal metadata, provenance, and the
mandatory-evidence rule for inferred facts — and the store maps rows to/from them
at boundaries.

Layering (doc 58): L0 contracts. Imports only ``pydantic`` and sibling L0 modules
(``graph.nodes``/``graph.edges`` enums, ``models.evidence``). It never imports the
KG L4 substrate, Memory, or Context, so upper layers depend on it, never the
reverse.

``KgNodeType``/``KgEdgeType`` are aliases of the canonical unified-graph enums
(decision: one enum set, not two competing ones — see design §Architecture
Decisions #2). The enums were expanded additively to cover OC-KG-001 §6-7.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from opencontext_core.compat import UTC
from opencontext_core.graph.edges import EdgeKind as KgEdgeType
from opencontext_core.graph.nodes import NodeKind as KgNodeType
from opencontext_core.models.evidence import EvidenceRef

__all__ = [
    "KgEdge",
    "KgEdgeType",
    "KgNode",
    "KgNodeType",
    "TemporalMetadata",
    "TemporalStatus",
    "kg_edge_id",
    "kg_node_id",
    "now_iso",
]

TemporalStatus = Literal["active", "stale", "superseded", "rejected"]

# Node kinds whose facts are inferred/observed (not derived directly from source
# structure) and therefore REQUIRE at least one EvidenceRef (OC-KG-001 §10-11).
# Structural code topology (file/class/function/...) is exempt.
_INFERRED_NODE_KINDS: frozenset[str] = frozenset(
    {
        KgNodeType.OWNER.value,
        KgNodeType.TEAM.value,
        KgNodeType.DECISION.value,
        KgNodeType.CONSTRAINT.value,
        KgNodeType.FAILURE_PATTERN.value,
        KgNodeType.MEMORY_BELIEF.value,
        KgNodeType.MEMORY_DECISION.value,
    }
)

# Edge kinds whose existence is inferred rather than read straight from source.
_INFERRED_EDGE_KINDS: frozenset[str] = frozenset(
    {
        KgEdgeType.OWNS.value,
        KgEdgeType.COVERS.value,
        KgEdgeType.DEPENDS_ON.value,
        KgEdgeType.CHANGED_BY.value,
        KgEdgeType.PRODUCED_BY.value,
        KgEdgeType.SUPPORTS.value,
        KgEdgeType.FAILED_WITH.value,
        KgEdgeType.SUPERSEDES.value,
        KgEdgeType.CONTRADICTS.value,
    }
)


def now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(tz=UTC).isoformat()


def kg_node_id(kind: str, name: str, path: str | None = None) -> str:
    """Content-addressed KG node id (``kg_<hash>``) per doc 59.

    Deterministic and dedup-safe: the same (kind, name, path) always maps to the
    same id, so re-observing a fact does not mint a duplicate node.
    """
    payload = f"{kind}|{name}|{path or ''}"
    return "kg_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def kg_edge_id(source_id: str, target_id: str, kind: str) -> str:
    """Content-addressed KG edge id (``kg_<hash>``) per doc 59."""
    payload = f"{source_id}|{target_id}|{kind}"
    return "kg_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class TemporalMetadata(BaseModel):
    """When a fact was observed and whether it is still valid (OC-KG-001 §10).

    Required on facts that change (ownership, decisions, commands, architecture
    constraints, failure patterns, runtime experience). ``supersede`` records the
    transition to a newer fact deterministically.
    """

    model_config = ConfigDict(extra="forbid")

    observed_at: str = Field(default_factory=now_iso, description="When the fact was observed.")
    valid_from: str | None = Field(default=None, description="Start of the validity window.")
    valid_to: str | None = Field(default=None, description="End of the validity window.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Fact confidence in [0,1].")
    superseded_by: str | None = Field(
        default=None, description="Id of the node/edge that supersedes this fact."
    )
    status: TemporalStatus = Field(default="active", description="Lifecycle status of the fact.")

    def supersede(self, by_id: str, *, at: str | None = None) -> TemporalMetadata:
        """Return a copy marked ``superseded`` by ``by_id`` (closing its window)."""
        stamp = at or now_iso()
        return self.model_copy(
            update={"status": "superseded", "superseded_by": by_id, "valid_to": stamp}
        )


class KgNode(BaseModel):
    """A typed, temporal, evidence-backed knowledge-graph node (OC-KG-001 §8)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Content-addressed node id (kg_<hash>).")
    type: KgNodeType = Field(description="Node kind from the unified KgNodeType set.")
    name: str = Field(description="Symbol/entity name.")
    path: str | None = Field(default=None, description="Project-relative path, when applicable.")
    language: str | None = Field(default=None, description="Source language, when applicable.")
    properties: dict[str, Any] = Field(default_factory=dict, description="Free-form properties.")
    temporal: TemporalMetadata = Field(
        default_factory=TemporalMetadata, description="Temporal metadata for changeable facts."
    )
    evidence: list[EvidenceRef] = Field(
        default_factory=list, description="Provenance for inferred facts."
    )
    structural: bool = Field(
        default=True,
        description="True for source-derived structure (evidence optional); "
        "False for inferred facts (evidence required).",
    )

    @model_validator(mode="after")
    def _require_evidence_for_inferred(self) -> KgNode:
        inferred = (not self.structural) or self.type.value in _INFERRED_NODE_KINDS
        if inferred and not self.evidence:
            raise ValueError(
                f"inferred KgNode {self.type.value!r} requires at least one EvidenceRef"
            )
        return self


class KgEdge(BaseModel):
    """A typed, temporal, evidence-backed knowledge-graph edge (OC-KG-001 §9)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Content-addressed edge id (kg_<hash>).")
    source_id: str = Field(description="Id of the source node.")
    target_id: str = Field(description="Id of the target node.")
    type: KgEdgeType = Field(description="Edge kind from the unified KgEdgeType set.")
    properties: dict[str, Any] = Field(default_factory=dict, description="Free-form properties.")
    temporal: TemporalMetadata = Field(
        default_factory=TemporalMetadata, description="Temporal metadata for changeable facts."
    )
    evidence: list[EvidenceRef] = Field(
        default_factory=list, description="Provenance for inferred relationships."
    )
    structural: bool = Field(
        default=True,
        description="True for source-derived relationships (CONTAINS/DEFINES/CALLS); "
        "False for inferred relationships (OWNS/COVERS/...) which require evidence.",
    )

    @model_validator(mode="after")
    def _require_evidence_for_inferred(self) -> KgEdge:
        inferred = (not self.structural) or self.type.value in _INFERRED_EDGE_KINDS
        if inferred and not self.evidence:
            raise ValueError(
                f"inferred KgEdge {self.type.value!r} requires at least one EvidenceRef"
            )
        return self
