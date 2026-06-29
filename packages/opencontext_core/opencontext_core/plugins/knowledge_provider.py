"""Pluggable KnowledgeProvider protocol + native SQLite provider (PR-008, KG-12).

OC-KG-001 §23 defines a full-lifecycle provider (``index``/``query``/
``retrieve_subgraph``/``apply_delta``) so the KG backend can be swapped — e.g. an
external graph DB through a plugin — without changing callers. The native SQLite
index is registered as the default provider; nothing requires an external DB
(book §22).

Layering (doc 58): plugin host (L11). It composes the KG L4 substrate, the L5 query
planner, and L0 models downward.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.indexing.graph_delta import GraphDelta
from opencontext_core.retrieval.query_planner import (
    ContextBudget,
    KgQueryPlan,
    KgQueryPlanner,
)
from opencontext_core.retrieval.subgraph import ContextSubgraph


class IndexOptions(BaseModel):
    """Options for a provider index run (OC-KG-001 §23)."""

    model_config = ConfigDict(extra="forbid")

    incremental: bool = Field(default=False, description="Reindex only changed files.")
    file_paths: list[str] = Field(
        default_factory=list, description="Files to (re)index when incremental."
    )


class IndexResult(BaseModel):
    """Result of a provider index run."""

    model_config = ConfigDict(extra="forbid")

    files_indexed: int = Field(default=0, description="Files indexed.")
    nodes: int = Field(default=0, description="Nodes written.")
    edges: int = Field(default=0, description="Edges written.")


class KgQuery(BaseModel):
    """A raw KG query (text + limit)."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="Query text.")
    limit: int = Field(default=20, gt=0, description="Maximum results.")


class KgQueryResult(BaseModel):
    """Result of a raw KG query: matched node summaries."""

    model_config = ConfigDict(extra="forbid")

    matches: list[dict[str, Any]] = Field(
        default_factory=list, description="Matched node rows (id/name/kind/path)."
    )


@runtime_checkable
class KnowledgeProvider(Protocol):
    """The provider lifecycle every KG backend implements (OC-KG-001 §23)."""

    def index(self, root: Path, options: IndexOptions) -> IndexResult: ...

    def query(self, query: KgQuery) -> KgQueryResult: ...

    def retrieve_subgraph(self, plan: KgQueryPlan) -> ContextSubgraph: ...

    def apply_delta(self, delta: GraphDelta) -> None: ...


class SqliteKnowledgeProvider:
    """Native default provider wrapping ``KnowledgeGraph`` + ``KgQueryPlanner``.

    Satisfies :class:`KnowledgeProvider` over the shipped SQLite + FTS index. This
    is the default backend; a plugin may register an alternative implementing the
    same protocol without changing callers (book §22).
    """

    name = "sqlite"

    def __init__(
        self,
        knowledge_graph: Any,
        *,
        available_capabilities: set[str] | None = None,
        observer: Any | None = None,
    ) -> None:
        self._kg = knowledge_graph
        self._planner = KgQueryPlanner(
            knowledge_graph,
            available_capabilities=available_capabilities,
            observer=observer,
        )

    def index(self, root: Path, options: IndexOptions) -> IndexResult:
        """Index ``root`` (or reindex ``options.file_paths`` when incremental)."""
        if options.incremental and options.file_paths:
            stats = self._kg.reindex_files(set(options.file_paths), Path(root))
            return IndexResult(
                files_indexed=stats.get("files", 0),
                nodes=stats.get("nodes", 0),
                edges=stats.get("edges", 0),
            )
        stats = self._kg.index_project(root)
        return IndexResult(
            files_indexed=stats.get("files_indexed", 0),
            nodes=stats.get("nodes", 0),
            edges=stats.get("edges", 0),
        )

    def query(self, query: KgQuery) -> KgQueryResult:
        """Run a raw FTS query against the native index."""
        rows = self._kg.search(query.text, limit=query.limit)
        return KgQueryResult(
            matches=[
                {
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "kind": r.get("kind"),
                    "path": r.get("file_path"),
                }
                for r in rows
            ]
        )

    def retrieve_subgraph(self, plan: KgQueryPlan) -> ContextSubgraph:
        """Materialise a budgeted subgraph for ``plan`` via the query planner."""
        return self._planner.retrieve_subgraph(plan)

    def apply_delta(self, delta: GraphDelta) -> None:
        """Apply a delta's deletions against the native store."""
        self._kg.apply_delta(delta)

    # Convenience: plan a query without a separate planner handle.
    def plan(
        self, task: str, workflow: str = "", node: str = "", budget: ContextBudget | None = None
    ) -> KgQueryPlan:
        """Build a task-aware :class:`KgQueryPlan` (delegates to the planner)."""
        return self._planner.plan(task, workflow, node, budget)


def native_provider(
    knowledge_graph: Any,
    *,
    available_capabilities: set[str] | None = None,
    observer: Any | None = None,
) -> SqliteKnowledgeProvider:
    """Return the default native :class:`KnowledgeProvider` for ``knowledge_graph``.

    The single registration point so callers depend on the protocol, not the class.
    """
    return SqliteKnowledgeProvider(
        knowledge_graph,
        available_capabilities=available_capabilities,
        observer=observer,
    )
