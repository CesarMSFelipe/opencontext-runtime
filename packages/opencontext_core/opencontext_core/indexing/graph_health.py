"""GraphHealthReport — structural health of the knowledge graph (Workstream E)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

GraphStatus = Literal["healthy", "degraded", "empty", "unavailable"]


class GraphHealthReport(BaseModel):
    """A deterministic, fail-closed snapshot of knowledge-graph health.

    Fail-closed: a missing or unreadable graph reports ``unavailable`` and an
    empty graph reports ``empty`` — never a silent "healthy".
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.graph_health.v1"
    status: GraphStatus
    indexed: bool
    nodes: int = Field(default=0, ge=0)
    edges: int = Field(default=0, ge=0)
    files: int = Field(default=0, ge=0)
    orphan_symbols: int = Field(default=0, ge=0)
    dangling_edges: int = Field(default=0, ge=0)
    languages: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    def ok(self) -> bool:
        return self.status == "healthy"


def compute_graph_health(db_path: str | Path) -> GraphHealthReport:
    """Build a :class:`GraphHealthReport` from the graph at ``db_path``.

    Reads only the persisted graph. Any DB-level failure degrades to
    ``unavailable`` rather than raising — health checks must never crash the
    caller (CI/doctor).
    """
    from opencontext_core.indexing.graph_db import GraphDatabase

    if not Path(db_path).exists():
        return GraphHealthReport(
            status="unavailable",
            indexed=False,
            warnings=[f"graph database not found: {db_path}"],
        )

    db = GraphDatabase(db_path=db_path)
    try:
        stats = db.get_stats()
        metrics = db.health_metrics()
        orphans = db.find_unused_symbols()
    except Exception as exc:  # fail-closed: a broken DB is "unavailable", not a crash
        return GraphHealthReport(
            status="unavailable",
            indexed=False,
            warnings=[f"graph health query failed: {exc}"],
        )
    finally:
        db.close()

    nodes = int(stats.get("nodes", 0))
    edges = int(stats.get("edges", 0))
    files = int(stats.get("files", 0))
    dangling = int(metrics.get("dangling_edges", 0))
    orphan_count = len(orphans)
    languages = dict(metrics.get("languages", {}))

    warnings: list[str] = []
    if nodes == 0:
        return GraphHealthReport(
            status="empty",
            indexed=False,
            nodes=0,
            edges=edges,
            files=files,
            languages=languages,
            warnings=["graph has no indexed symbols — run `opencontext index .`"],
        )

    status: GraphStatus = "healthy"
    if dangling > 0:
        status = "degraded"
        warnings.append(f"{dangling} dangling edge(s) — index may be stale; re-index to clean up")
    # Orphan ratio is advisory (string-dispatched entry points can look orphan),
    # but a very high ratio is worth surfacing.
    if nodes and orphan_count / nodes > 0.5:
        status = "degraded"
        warnings.append(
            f"{orphan_count}/{nodes} symbols have no inbound reference (advisory)"
        )

    return GraphHealthReport(
        status=status,
        indexed=True,
        nodes=nodes,
        edges=edges,
        files=files,
        orphan_symbols=orphan_count,
        dangling_edges=dangling,
        languages=languages,
        warnings=warnings,
    )
