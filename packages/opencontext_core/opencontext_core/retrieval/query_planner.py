"""Task-aware KG query planner + named retrieval modes (PR-008, KG-09/KG-10).

The KG must not expose only raw graph queries (OC-KG-001 §16). ``KgQueryPlanner``
selects a retrieval *mode* and traversal shape from the workflow node and task type,
then ``retrieve_subgraph`` materialises a budgeted :class:`ContextSubgraph` over the
native index — reusing the existing ranking where helpful and adding the typed,
mode-aware, node-budgeted shape on top.

Capability-graph linkage (KG-CONV): ``plan`` accepts an injected set of available
capability ids. When the environment has no test runner, the test-dependent
``test_first`` mode degrades gracefully to ``symbol_first`` (doc 58: the consumer
takes a plain ``set[str]``, never the CapabilityGraph internals).

Layering (doc 58): retrieval/Context layer (L5). It reads the KG L4 substrate
downward and composes L0 models; it never imports Memory.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.indexing.graph_db import is_test_path
from opencontext_core.models.evidence import EvidenceRef
from opencontext_core.models.kg_v2 import KgEdge, KgNode, KgNodeType, kg_edge_id, kg_node_id
from opencontext_core.retrieval.subgraph import ContextSubgraph, build_context_subgraph

RetrievalMode = Literal[
    "symbol_first",
    "test_first",
    "owner_first",
    "failure_first",
    "decision_first",
    "architecture_boundary",
]

ALL_RETRIEVAL_MODES: tuple[RetrievalMode, ...] = (
    "symbol_first",
    "test_first",
    "owner_first",
    "failure_first",
    "decision_first",
    "architecture_boundary",
)

# Capability ids that satisfy "a test runner is present" (KG-CONV capability link).
_TEST_RUNNER_CAPABILITIES: frozenset[str] = frozenset(
    {"pytest", "jest", "vitest", "phpunit", "go-test", "test"}
)


class ContextBudget(BaseModel):
    """Node + token budget for a KG query (OC-KG-001 §16/§18)."""

    model_config = ConfigDict(extra="forbid")

    max_nodes: int = Field(default=20, gt=0, description="Maximum nodes in the subgraph.")
    max_tokens: int = Field(default=4000, gt=0, description="Maximum token budget.")


class KgQueryPlan(BaseModel):
    """A task-aware KG query plan (OC-KG-001 §16)."""

    model_config = ConfigDict(extra="forbid")

    task: str = Field(description="The task driving retrieval.")
    workflow: str = Field(default="", description="Workflow id (e.g. sdd, oc-flow).")
    node: str = Field(default="", description="Workflow node (e.g. verify, apply).")
    mode: RetrievalMode = Field(description="Selected retrieval mode.")
    budget: ContextBudget = Field(description="Node + token budget for the query.")
    target: str = Field(default="", description="Primary target identifier, if any.")
    radius: int = Field(default=1, ge=0, description="Traversal radius around the target.")
    degraded_from: RetrievalMode | None = Field(
        default=None,
        description="Mode the plan degraded from when a capability was unavailable.",
    )


def _select_mode(workflow: str, node: str, task: str) -> RetrievalMode:
    """Select a retrieval mode from the workflow node and task type (§17).

    Deterministic keyword routing. The workflow node dominates (a ``verify`` node
    always wants tests first); otherwise the task text decides.
    """
    n = node.lower()
    t = task.lower()
    if n in ("verify", "test", "tdd") or "test" in t or "coverage" in t:
        return "test_first"
    if n in ("owner", "review") or "owner" in t or "who owns" in t or "responsible" in t:
        return "owner_first"
    if "fail" in t or "bug" in t or "regression" in t or "broke" in t or n == "debug":
        return "failure_first"
    if "decision" in t or "why" in t or "rationale" in t or n in ("propose", "design"):
        return "decision_first"
    if "architecture" in t or "boundary" in t or "module" in t or "dependenc" in t:
        return "architecture_boundary"
    return "symbol_first"


class KgQueryPlanner:
    """Plans and executes task-aware KG retrieval over the native index."""

    # Subgraph confidence at or below this is reported via kg.confidence.low (§19).
    LOW_CONFIDENCE_THRESHOLD = 0.3

    def __init__(
        self,
        knowledge_graph: Any,
        *,
        available_capabilities: set[str] | None = None,
        observer: Any | None = None,
    ) -> None:
        # ``knowledge_graph`` is a KnowledgeGraph (typed loosely to avoid an import
        # cycle through the facade). ``available_capabilities`` is the injected
        # CapabilityGraph readiness set (KG-CONV); None disables degradation.
        # ``observer`` is an optional KgObserver collecting kg.* events / receipts.
        self._kg = knowledge_graph
        self._capabilities = available_capabilities
        self._observer = observer

    def plan(
        self,
        task: str,
        workflow: str = "",
        node: str = "",
        budget: ContextBudget | None = None,
    ) -> KgQueryPlan:
        """Return a :class:`KgQueryPlan` for ``task`` at ``workflow``/``node``.

        Selects the retrieval mode (§17), then applies capability-graph degradation
        (KG-CONV): if ``test_first`` is selected but no test runner is available,
        the plan degrades to ``symbol_first`` and records the original mode.
        """
        mode = _select_mode(workflow, node, task)
        degraded_from: RetrievalMode | None = None
        if mode == "test_first" and not self._test_runner_available():
            degraded_from = mode
            mode = "symbol_first"
        return KgQueryPlan(
            task=task,
            workflow=workflow,
            node=node,
            mode=mode,
            budget=budget or ContextBudget(),
            target=_primary_identifier(task),
            degraded_from=degraded_from,
        )

    def available_modes(self) -> list[RetrievalMode]:
        """Modes available given the injected capabilities (KG-CONV).

        ``test_first`` is dropped when no test runner is present; the rest are always
        available. With no capability set injected, all modes are available.
        """
        if self._test_runner_available():
            return list(ALL_RETRIEVAL_MODES)
        return [m for m in ALL_RETRIEVAL_MODES if m != "test_first"]

    def _test_runner_available(self) -> bool:
        if self._capabilities is None:
            return True  # no capability graph injected: do not degrade
        return bool(self._capabilities & _TEST_RUNNER_CAPABILITIES)

    def retrieve_subgraph(self, plan: KgQueryPlan) -> ContextSubgraph:
        """Materialise a budgeted :class:`ContextSubgraph` for ``plan``.

        Pulls candidate symbol rows from the native FTS/name index, maps them to KG
        v2 nodes, reorders them by the plan's mode (e.g. ``test_first`` floats test
        nodes ahead), folds in owner nodes for ``owner_first``, then enforces the
        node + token budgets via :func:`build_context_subgraph`.
        """
        db = self._kg.db
        query = plan.task
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()

        # Name-anchored recall for the target identifier, then BM25 over the task.
        if plan.target:
            for row in db.search_symbols_by_name([plan.target], limit=plan.budget.max_nodes * 2):
                if row["id"] not in seen:
                    seen.add(row["id"])
                    rows.append(row)
        for row in db.search_fts(query, limit=plan.budget.max_nodes * 3):
            if row["id"] not in seen:
                seen.add(row["id"])
                rows.append(row)

        nodes = [_row_to_kg_node(row) for row in rows]
        owner_nodes = self._owner_nodes(rows) if plan.mode == "owner_first" else []
        ordered = _order_for_mode(plan.mode, nodes, owner_nodes)

        edges = self._edges_among(db, [n.id for n in ordered])
        target_lc = plan.target.lower()
        exact_match = any(n.name.lower() == target_lc for n in ordered) if plan.target else False
        tests_found = any(_is_test_node(n) for n in ordered)
        owners_found = any(n.type == KgNodeType.OWNER for n in ordered)

        if self._observer is not None:
            from opencontext_core.models.trace import KG_QUERY_STARTED

            self._observer.emit(KG_QUERY_STARTED, mode=plan.mode, target=plan.target)

        subgraph = build_context_subgraph(
            ordered,
            max_nodes=plan.budget.max_nodes,
            max_tokens=plan.budget.max_tokens,
            edges=edges,
            exact_match=exact_match,
            tests_found=tests_found,
            owners_found=owners_found,
            fresh=True,
        )
        self._observe_retrieval(plan, subgraph)
        return subgraph

    def _observe_retrieval(self, plan: KgQueryPlan, subgraph: ContextSubgraph) -> None:
        """Emit kg.subgraph.created / kg.confidence.low / kg.query.completed + receipt.

        No-op when no observer is attached (legacy path). Records that a subgraph
        served the request and no broad file read was needed (KG-CONV).
        """
        observer = self._observer
        if observer is None:
            return
        from opencontext_core.models.trace import (
            KG_CONFIDENCE_LOW,
            KG_QUERY_COMPLETED,
            KG_SUBGRAPH_CREATED,
        )

        observer.emit(
            KG_SUBGRAPH_CREATED,
            nodes=len(subgraph.nodes),
            omitted=len(subgraph.omitted),
            confidence=subgraph.confidence,
        )
        if subgraph.confidence <= self.LOW_CONFIDENCE_THRESHOLD:
            observer.emit(KG_CONFIDENCE_LOW, confidence=subgraph.confidence, mode=plan.mode)
        observer.emit(KG_QUERY_COMPLETED, mode=plan.mode, nodes=len(subgraph.nodes))
        if hasattr(observer, "write_receipt"):
            observer.write_receipt(
                "retrieval",
                mode=plan.mode,
                nodes=len(subgraph.nodes),
                confidence=subgraph.confidence,
                subgraph_used=True,
                broad_file_read=False,
            )

    def _owner_nodes(self, rows: list[dict[str, Any]]) -> list[KgNode]:
        """Resolve OWNER nodes for the candidate rows' files via the graph (KG-CONV)."""
        owners: dict[str, KgNode] = {}
        for row in rows:
            path = row.get("file_path")
            if not path:
                continue
            owner = self._kg.resolve_owner(path)
            if not owner:
                continue
            oid = kg_node_id("owner", owner)
            if oid in owners:
                continue
            owners[oid] = KgNode(
                id=oid,
                type=KgNodeType.OWNER,
                name=owner,
                path=path,
                structural=False,
                evidence=[
                    EvidenceRef(
                        source=path,
                        source_type="commit",
                        confidence=0.7,
                        path=path,
                    )
                ],
            )
        return list(owners.values())

    @staticmethod
    def _edges_among(db: Any, node_ids: list[str]) -> list[KgEdge]:
        """Fetch typed edges whose endpoints are both in ``node_ids``."""
        if not node_ids:
            return []
        from opencontext_core.models.kg_v2 import KgEdgeType

        ids = set(node_ids)
        conn = db._connect()
        placeholders = ",".join("?" * len(node_ids))
        rows = conn.execute(
            "SELECT source_node_id, target_node_id, kind FROM edges "
            f"WHERE source_node_id IN ({placeholders}) AND target_node_id IS NOT NULL",
            list(node_ids),
        ).fetchall()
        edges: list[KgEdge] = []
        for r in rows:
            if r["target_node_id"] not in ids:
                continue
            try:
                kind = KgEdgeType(r["kind"])
            except ValueError:
                kind = KgEdgeType.REFERENCES
            edges.append(
                KgEdge(
                    id=kg_edge_id(r["source_node_id"], r["target_node_id"], kind.value),
                    source_id=r["source_node_id"],
                    target_id=r["target_node_id"],
                    type=kind,
                    structural=True,
                )
            )
        return edges


# --- mode ordering helpers ----------------------------------------------------

_DEFINITION_KINDS = frozenset(
    {
        KgNodeType.CLASS,
        KgNodeType.FUNCTION,
        KgNodeType.METHOD,
        KgNodeType.INTERFACE,
        KgNodeType.SYMBOL,
        KgNodeType.CODE_SYMBOL,
    }
)
_BOUNDARY_KINDS = frozenset(
    {
        KgNodeType.MODULE,
        KgNodeType.PACKAGE,
        KgNodeType.INTERFACE,
        KgNodeType.SERVICE,
        KgNodeType.ROUTE,
    }
)


def _is_test_node(node: KgNode) -> bool:
    return node.type == KgNodeType.TEST or (bool(node.path) and is_test_path(node.path or ""))


def _order_for_mode(
    mode: RetrievalMode, nodes: list[KgNode], owner_nodes: list[KgNode]
) -> list[KgNode]:
    """Stable reorder of ``nodes`` putting the mode's preferred kind first.

    The input order (name-anchored, then BM25) is the relevance baseline; each mode
    applies a stable partition that floats its preferred nodes ahead without
    discarding the rest, so retrieval degrades to symbol relevance when the mode's
    target kind is absent.
    """
    if mode == "owner_first":
        return [*owner_nodes, *nodes]
    if mode == "test_first":
        return _stable_partition(nodes, _is_test_node)
    if mode == "failure_first":
        return _stable_partition(nodes, lambda n: n.type == KgNodeType.FAILURE_PATTERN)
    if mode == "decision_first":
        return _stable_partition(nodes, lambda n: n.type == KgNodeType.DECISION)
    if mode == "architecture_boundary":
        return _stable_partition(nodes, lambda n: n.type in _BOUNDARY_KINDS)
    # symbol_first: definitions lead.
    return _stable_partition(nodes, lambda n: n.type in _DEFINITION_KINDS)


def _stable_partition(nodes: list[KgNode], pred: Any) -> list[KgNode]:
    """Return ``nodes`` with ``pred``-true entries first, preserving relative order."""
    head = [n for n in nodes if pred(n)]
    tail = [n for n in nodes if not pred(n)]
    return [*head, *tail]


def _row_to_kg_node(row: dict[str, Any]) -> KgNode:
    """Map an index search row (dict) to a KG v2 structural :class:`KgNode`."""
    name = row.get("name", "")
    path = row.get("file_path")
    try:
        kind = KgNodeType(row.get("kind", ""))
    except ValueError:
        kind = KgNodeType.SYMBOL
    return KgNode(
        id=str(row.get("id") or kg_node_id(kind.value, name, path)),
        type=kind,
        name=name,
        path=path,
        language=row.get("language"),
        properties={
            "line": row.get("line"),
            "container": row.get("container"),
            "signature": row.get("signature"),
        },
        structural=True,
    )


def _primary_identifier(task: str) -> str:
    """Best-effort primary identifier the task is about (CamelCase/snake_case token).

    Returns the first identifier-shaped token, else the longest alpha word, else "".
    """
    import re

    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", task):
        token = str(token)
        if len(token) < 3:
            continue
        if "_" in token or any(c.isupper() for c in token[1:]) or token[0].isupper():
            return token
    words: list[str] = [str(w) for w in re.findall(r"[A-Za-z]{3,}", task)]
    return max(words, key=len) if words else ""
