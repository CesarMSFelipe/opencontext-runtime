"""KG-v2 "consult the graph before broad file reads" entry point (PR-008, KG-09/14).

A thin, flag-gated bridge the Context Harness / OC Flow ``gather_context`` calls to
get a budgeted :class:`ContextSubgraph` from the native index BEFORE falling back to
broad file reads (OC-KG-001 §16-18). Returns ``None`` when v2 is disabled, the index
is absent, or the subgraph is empty, so the caller falls back to the legacy
``RetrievalPlanner`` path verbatim.

Layering (doc 58): retrieval/Context layer (L5). Opens the KG L4 substrate downward.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_core.retrieval.query_planner import ContextBudget, KgQueryPlanner
from opencontext_core.retrieval.subgraph import ContextSubgraph


def kg_first_subgraph(
    task: str,
    graph_db_path: str | Path,
    *,
    max_nodes: int = 20,
    max_tokens: int = 4000,
    workflow: str = "",
    node: str = "",
    available_capabilities: set[str] | None = None,
    observer: Any | None = None,
) -> ContextSubgraph | None:
    """Return a budgeted KG subgraph for ``task``, or None to fall back to files.

    Builds a task-aware plan over the native SQLite index and retrieves a budgeted
    subgraph. ``observer`` (a ``KgObserver``) receives the kg.query / kg.subgraph
    events + a retrieval receipt recording that the subgraph served the request and
    no broad file read was needed (KG-CONV). Best-effort: any failure returns None.
    """
    db_path = Path(graph_db_path)
    if not db_path.exists():
        return None
    try:
        from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(db_path=db_path)
    except Exception:
        return None
    try:
        planner = KgQueryPlanner(
            kg, available_capabilities=available_capabilities, observer=observer
        )
        plan = planner.plan(
            task,
            workflow,
            node,
            ContextBudget(max_nodes=max_nodes, max_tokens=max_tokens),
        )
        subgraph = planner.retrieve_subgraph(plan)
        return subgraph if subgraph.nodes else None
    except Exception:
        return None
    finally:
        kg.close()
