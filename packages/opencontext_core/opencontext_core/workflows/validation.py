"""Workflow graph validation (spec VAL1) and convergence compatibility checks.

Validation fails early — on ``register()`` and on YAML load — so invalid
definitions never reach resolution (design: "fail early"). Layer L6; imports only
the L6 definition module and L0 contracts.
"""

from __future__ import annotations

from collections import deque

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.workflows.definition import WorkflowDefinition


class WorkflowValidationError(ValueError):
    """Raised when a workflow definition fails structural validation."""


class WorkflowProfileError(ValueError):
    """Raised when a profile is incompatible with a workflow (WR-CONV)."""


class WorkflowCapabilityError(ValueError):
    """Raised when a required capability is unavailable (WR-CONV)."""


def ensure_unique_node_ids(node_ids: list[str]) -> None:
    """Raise ``WorkflowValidationError`` if ``node_ids`` contains a duplicate.

    Used by the YAML loader (where nodes arrive as a list) and exercisable
    directly — a Python ``dict`` cannot express duplicate keys, so duplicate
    detection lives at the point a list is parsed.
    """
    seen: set[str] = set()
    for node_id in node_ids:
        if node_id in seen:
            raise WorkflowValidationError(f"duplicate node id: {node_id!r}")
        seen.add(node_id)


def validate(defn: WorkflowDefinition) -> None:
    """Validate a workflow definition's structural integrity (spec VAL1).

    Rejects a definition when: ``schema_version``/``id`` is missing, the
    ``start_node`` is absent from ``nodes``, any ``terminal_node`` is absent, any
    edge references an unknown node, a node's id disagrees with its key, a ``role``
    is not a string, or a node is unreachable from the start node (unless
    ``metadata.allow_unreachable`` is set).
    """
    if not defn.schema_version:
        raise WorkflowValidationError("schema_version is required")
    if not defn.id:
        raise WorkflowValidationError("id is required")

    nodes = defn.nodes
    if not nodes:
        raise WorkflowValidationError(f"workflow {defn.id!r} has no nodes")

    # Node id/key consistency + role typing.
    for key, node in nodes.items():
        if node.id != key:
            raise WorkflowValidationError(f"node key {key!r} disagrees with node id {node.id!r}")
        if not isinstance(node.role, str) or not node.role:
            raise WorkflowValidationError(f"node {key!r} role must be a non-empty string")

    if defn.start_node not in nodes:
        raise WorkflowValidationError(f"start_node {defn.start_node!r} is not a declared node")

    if not defn.terminal_nodes:
        raise WorkflowValidationError(f"workflow {defn.id!r} declares no terminal_nodes")
    for terminal in defn.terminal_nodes:
        if terminal not in nodes:
            raise WorkflowValidationError(f"terminal_node {terminal!r} is not a declared node")

    # Edge endpoint references.
    for edge in defn.edges:
        if edge.from_node not in nodes:
            raise WorkflowValidationError(
                f"edge from unknown node {edge.from_node!r} -> {edge.to_node!r}"
            )
        if edge.to_node not in nodes:
            raise WorkflowValidationError(
                f"edge {edge.from_node!r} -> unknown node {edge.to_node!r}"
            )

    # Phase-subset profiles must reference declared nodes.
    for profile_name, profile_nodes in defn.profiles.items():
        for node_id in profile_nodes:
            if node_id not in nodes:
                raise WorkflowValidationError(
                    f"profile {profile_name!r} references unknown node {node_id!r}"
                )

    # Reachability from start_node (BFS over edges).
    if not defn.metadata.get("allow_unreachable", False):
        reachable = _reachable_from(defn.start_node, defn)
        unreachable = sorted(set(nodes) - reachable)
        if unreachable:
            raise WorkflowValidationError(
                f"unreachable nodes from {defn.start_node!r}: {', '.join(unreachable)}"
            )


def _reachable_from(start: str, defn: WorkflowDefinition) -> set[str]:
    """Breadth-first set of node ids reachable from ``start`` over forward edges."""
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in defn.nodes}
    for edge in defn.edges:
        if edge.from_node in adjacency:
            adjacency[edge.from_node].append(edge.to_node)
    seen: set[str] = {start}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for nxt in adjacency.get(current, []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def validate_profile(defn: WorkflowDefinition, profile: str) -> None:
    """Reject a profile incompatible with the workflow (WR-CONV).

    An empty ``compatible_profiles`` means any profile is allowed.
    """
    if defn.compatible_profiles and profile not in defn.compatible_profiles:
        raise WorkflowProfileError(
            f"profile {profile!r} is not compatible with workflow {defn.id!r}; "
            f"allowed: {', '.join(defn.compatible_profiles)}"
        )


def missing_capabilities(defn: WorkflowDefinition, available: set[str]) -> list[str]:
    """Return the workflow's required capabilities not present in ``available``."""
    return [cap for cap in defn.required_capabilities if cap not in available]


class CoexistenceReport(BaseModel):
    """Result of validating that multiple workflow kinds share runtime infra."""

    model_config = ConfigDict(extra="forbid")

    ok: bool = Field(description="True when all kinds coexist over shared infra.")
    kinds: list[str] = Field(default_factory=list, description="Distinct workflow kinds present.")
    shared_runner: str = Field(description="The single runner all kinds delegate to.")
    shared_event_ledger: str = Field(description="The single event ledger all kinds write.")
    shared_receipt: str = Field(description="The single receipt seam all kinds write.")
    duplicated_seams: list[str] = Field(
        default_factory=list, description="Seams a definition duplicated instead of sharing."
    )


# The single, shared runtime seams every workflow kind delegates to (invariant 9.2:
# SDD and OC Flow share infrastructure; no per-kind runner/event/receipt).
_SHARED_RUNNER = "HarnessRunner"
_SHARED_EVENT_LEDGER = "events.json"
_SHARED_RECEIPT = "workflow-selection.json"


def validate_coexistence(definitions: list[WorkflowDefinition]) -> CoexistenceReport:
    """Assert SDD and OC-Flow workflows coexist over shared infra (WR-CONV).

    A definition that pins its own ``runner``/``event_store``/``receipt_store`` in
    metadata to a value other than the shared seam is flagged as duplicating
    infrastructure (invariant 9.2 violation).
    """
    duplicated: list[str] = []
    for defn in definitions:
        validate(defn)
        meta = defn.metadata
        runner = meta.get("runner")
        if runner is not None and runner != _SHARED_RUNNER:
            duplicated.append(f"{defn.id}:runner={runner}")
        event_store = meta.get("event_store")
        if event_store is not None and event_store != _SHARED_EVENT_LEDGER:
            duplicated.append(f"{defn.id}:event_store={event_store}")
        receipt_store = meta.get("receipt_store")
        if receipt_store is not None and receipt_store != _SHARED_RECEIPT:
            duplicated.append(f"{defn.id}:receipt_store={receipt_store}")

    kinds = sorted({defn.kind for defn in definitions})
    return CoexistenceReport(
        ok=not duplicated,
        kinds=kinds,
        shared_runner=_SHARED_RUNNER,
        shared_event_ledger=_SHARED_EVENT_LEDGER,
        shared_receipt=_SHARED_RECEIPT,
        duplicated_seams=duplicated,
    )
