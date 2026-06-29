"""Canonical three-layer Context Envelope (PR-010, OC-CONTEXT-001 §6).

This is the single canonical :class:`ContextEnvelope` for the runtime — the typed
contract every workflow node receives from the Context Engine. It carries the book
§6 shape verbatim: three context layers (``l3`` structural / ``l2`` task contract /
``l1`` ephemeral) plus a deterministic ``token_estimate``, the ``evidence_refs``
provenance, the explicit ``omissions``, and a normalized ``confidence``.

Reconciliation (book NOTE): PR-007 left a surgical ``ContextEnvelope`` seam in
``oc_flow/models.py`` with a flat ``items``/``omissions`` shape. That one is now a
*projection* of this canonical envelope; the bridge that derives it lives in
``context/engine.py`` (an upper layer) so this L0 model stays a pure leaf — it
imports only pydantic and the L0 evidence/context models, never oc_flow upward.

Layering (doc 58): L0 data model. Depended on by the Context Engine (L5) and by
Runtime Intelligence (PR-011); it depends on nothing above L0.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.models.context import ContextOmission
from opencontext_core.models.evidence import EvidenceRef

# Context contract version (doc 59 — internal contract versioning). Bump on a
# breaking change to the envelope shape; a guard test asserts the value.
CONTEXT_CONTRACT_VERSION = 1


class ContextEnvelope(BaseModel):
    """The minimal-sufficient typed context delivered to a workflow node (book §6).

    ``l3``/``l2``/``l1`` keep the book's ``dict`` wire shape but are built by typed
    assemblers (see :class:`~opencontext_core.context.engine.ContextEngine`) and
    key-validated in tests:

    - ``l3`` — structural context: repository topology, package boundaries, symbol
      signatures, owners, architecture decisions, public contracts. Source: KG.
    - ``l2`` — the immutable task contract: acceptance criteria, constraints,
      verification strategy, risk, required artifacts. Immutable during execution.
    - ``l1`` — ephemeral working context: focused files, snippets, diagnostics,
      stack traces, changed symbols, targeted tests. Purged after consolidation.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="opencontext.context.v1",
        description="Stable envelope schema id (book §6).",
    )
    workflow: str = Field(default="", description="Workflow the envelope was built for.")
    node: str = Field(default="", description="Workflow node the envelope was built for.")
    task: str = Field(default="", description="Task statement the context serves.")
    l3: dict[str, Any] = Field(default_factory=dict, description="Structural context (KG).")
    l2: dict[str, Any] = Field(default_factory=dict, description="Immutable task contract.")
    l1: dict[str, Any] = Field(default_factory=dict, description="Ephemeral working context.")
    token_estimate: int = Field(
        default=0, ge=0, description="Deterministic total token estimate for the envelope."
    )
    evidence_refs: list[EvidenceRef] = Field(
        default_factory=list, description="Provenance for the included context."
    )
    omissions: list[ContextOmission] = Field(
        default_factory=list, description="Every item deliberately left out, with a reason."
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Normalized envelope confidence [0,1]."
    )

    def purge_l1(self) -> ContextEnvelope:
        """Return a copy with ``l1`` emptied (book invariant: L1 is ephemeral).

        ``l2`` (immutable contract) and ``l3`` (structural) are preserved verbatim,
        so a consolidated node can drop its working set without losing the contract.
        """
        return self.model_copy(update={"l1": {}})
