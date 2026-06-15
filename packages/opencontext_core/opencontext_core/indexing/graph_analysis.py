"""Deterministic graph analysis over the persisted ``nodes``/``edges`` tables.

Computes in/out-degree centrality, flags high-centrality "god nodes" above a
configurable threshold, partitions nodes into communities by connectivity
(connected components refined by label propagation), and exposes name-resolving
``path``/``explain`` queries built on :class:`CallGraphAnalyzer`.

Zero new hard dependencies: everything runs on the standard library and the
existing :class:`GraphDatabase` SQLite connection. ``networkx`` is used only if
it is already importable (purely optional); the pure-Python path is the default
and is the one exercised by the tests. Results are reproducible for identical
graph content because every traversal iterates in a deterministic, sorted order.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from opencontext_core.indexing.call_graph import CallGraphAnalyzer, PathResult
from opencontext_core.indexing.graph_db import GraphDatabase


@dataclass(frozen=True)
class Centrality:
    """In/out-degree centrality for a single node."""

    node_id: str
    name: str
    in_degree: int
    out_degree: int
    score: float


@dataclass(frozen=True)
class GodNode:
    """A node flagged as a high-centrality "god node"."""

    node_id: str
    name: str
    in_degree: int
    out_degree: int
    score: float


@dataclass
class Explanation:
    """Relationship summary for a single symbol (callers, callees, shortest path)."""

    symbol: str
    resolved: bool
    node_id: str | None = None
    callers: list[dict[str, Any]] = field(default_factory=list)
    callees: list[dict[str, Any]] = field(default_factory=list)
    god_node: bool = False
    centrality: float = 0.0


class GraphAnalyzer:
    """Derived analysis over a populated :class:`GraphDatabase`.

    The analyzer owns the passed database handle and closes it via
    :meth:`close`; callers that share a handle should manage the lifetime
    themselves and avoid :meth:`close`.
    """

    def __init__(self, db: GraphDatabase, *, edge_kinds: tuple[str, ...] = ("calls",)) -> None:
        self.db = db
        self._edge_kinds = edge_kinds
        self._call_graph = CallGraphAnalyzer(db)

    def close(self) -> None:
        self.db.close()

    # ---- graph loading -------------------------------------------------

    def _load_edges(self) -> list[tuple[str, str]]:
        """Return ``(source_id, target_id)`` pairs, sorted for determinism."""
        conn = self.db._connect()
        placeholders = ",".join("?" for _ in self._edge_kinds)
        rows = conn.execute(
            f"""
            SELECT source_node_id, target_node_id
            FROM edges
            WHERE kind IN ({placeholders}) AND target_node_id IS NOT NULL
            """,
            tuple(self._edge_kinds),
        ).fetchall()
        edges = [
            (str(r["source_node_id"]), str(r["target_node_id"]))
            for r in rows
            if r["target_node_id"] is not None
        ]
        return sorted(edges)

    def _load_node_names(self) -> dict[str, str]:
        conn = self.db._connect()
        rows = conn.execute("SELECT id, name FROM nodes").fetchall()
        return {str(r["id"]): (r["name"] or "") for r in rows}

    # ---- centrality / god nodes ---------------------------------------

    def compute_centrality(self) -> dict[str, Centrality]:
        """Compute deterministic in/out-degree centrality for every node.

        ``score`` is degree centrality normalized by the maximum possible degree
        (``n - 1`` over ``n`` nodes), weighting in-degree (fan-in) twice as
        heavily as out-degree because fan-in is the dominant blast-radius signal.
        With a single node (no edges possible) the score is ``0.0``.
        """
        names = self._load_node_names()
        edges = self._load_edges()
        in_deg: dict[str, int] = defaultdict(int)
        out_deg: dict[str, int] = defaultdict(int)
        for src, dst in edges:
            out_deg[src] += 1
            in_deg[dst] += 1

        n = len(names)
        denom = float(n - 1) if n > 1 else 1.0
        result: dict[str, Centrality] = {}
        for node_id in sorted(names):
            i = in_deg.get(node_id, 0)
            o = out_deg.get(node_id, 0)
            score = (2.0 * i + o) / (3.0 * denom) if n > 1 else 0.0
            result[node_id] = Centrality(
                node_id=node_id,
                name=names[node_id],
                in_degree=i,
                out_degree=o,
                score=score,
            )
        return result

    def detect_god_nodes(self, threshold: int = 8) -> list[GodNode]:
        """Flag nodes whose total degree (in + out) is at least ``threshold``.

        Returned in descending centrality order (then node id) so the result is
        deterministic for identical graph content.
        """
        centrality = self.compute_centrality()
        gods = [
            GodNode(
                node_id=c.node_id,
                name=c.name,
                in_degree=c.in_degree,
                out_degree=c.out_degree,
                score=c.score,
            )
            for c in centrality.values()
            if (c.in_degree + c.out_degree) >= threshold
        ]
        gods.sort(key=lambda g: (-g.score, g.node_id))
        return gods

    # ---- community detection ------------------------------------------

    def detect_communities(self, *, max_iterations: int = 100) -> dict[str, int]:
        """Partition nodes into communities by connectivity.

        Connected components (treating call edges as undirected) bound the
        partition — nodes in different components never share a community — and
        label propagation refines each component. Both phases iterate in sorted
        order with deterministic tie-breaks, so the assignment is identical
        across repeated runs on the same graph. Community ids are small ints
        assigned in ascending order of each community's smallest node id.
        """
        names = self._load_node_names()
        edges = self._load_edges()
        adjacency: dict[str, set[str]] = {nid: set() for nid in names}
        for src, dst in edges:
            if src in adjacency and dst in adjacency:
                adjacency[src].add(dst)
                adjacency[dst].add(src)

        # connected components (deterministic BFS over sorted nodes).
        component: dict[str, int] = {}
        comp_id = 0
        for start in sorted(names):
            if start in component:
                continue
            queue: deque[str] = deque([start])
            component[start] = comp_id
            while queue:
                node = queue.popleft()
                for neighbor in sorted(adjacency[node]):
                    if neighbor not in component:
                        component[neighbor] = comp_id
                        queue.append(neighbor)
            comp_id += 1

        # label propagation, seeded by component + node id and bounded
        # to its component so labels never leak across components.
        labels: dict[str, str] = {nid: nid for nid in sorted(names)}
        for _ in range(max_iterations):
            changed = False
            for node in sorted(names):
                neighbor_labels: dict[str, int] = defaultdict(int)
                for neighbor in adjacency[node]:
                    neighbor_labels[labels[neighbor]] += 1
                if not neighbor_labels:
                    continue
                # Pick the most frequent neighbor label; tie-break on the
                # lexicographically smallest label for reproducibility.
                best = min(neighbor_labels.items(), key=lambda kv: (-kv[1], kv[0]))[0]
                if best != labels[node]:
                    labels[node] = best
                    changed = True
            if not changed:
                break

        # Canonicalize: a community is (component, propagated label). Number them
        # by the smallest member node id so ids are stable and contiguous.
        raw_groups: dict[tuple[int, str], list[str]] = defaultdict(list)
        for node in sorted(names):
            raw_groups[(component[node], labels[node])].append(node)
        ordered = sorted(raw_groups.values(), key=lambda members: min(members))
        partition: dict[str, int] = {}
        for community_id, members in enumerate(ordered):
            for node in members:
                partition[node] = community_id
        return partition

    # ---- name-resolving path / explain --------------------------------

    def _resolve_name(self, name: str) -> list[str]:
        """Return all node ids matching ``name`` exactly, sorted for determinism."""
        conn = self.db._connect()
        rows = conn.execute("SELECT id FROM nodes WHERE name = ? ORDER BY id", (name,)).fetchall()
        return [str(r["id"]) for r in rows]

    def path(self, source_name: str, target_name: str, *, max_depth: int = 10) -> PathResult:
        """Shortest directed call path between two named symbols.

        Resolves each name to its stable node id(s) and delegates to
        :meth:`CallGraphAnalyzer.find_path`. When a name is ambiguous, the
        first resolvable pair (sorted) that yields a path wins; if none yield a
        path, the last attempt's result (found=False) is returned. Reports
        ``found=False`` rather than raising when no path exists, and surfaces
        ``depth_exceeded`` when the search was truncated by ``max_depth``.
        """
        sources = self._resolve_name(source_name)
        targets = self._resolve_name(target_name)
        if not sources or not targets:
            return PathResult(found=False)

        last = PathResult(found=False)
        for src in sources:
            for dst in targets:
                result = self._call_graph.find_path(src, dst, max_depth=max_depth)
                if result.found:
                    return result
                last = result
        return last

    def explain(self, name: str, *, god_node_threshold: int = 8) -> Explanation:
        """Describe a symbol: its callers, callees, and centrality/god status.

        Reports ``resolved=False`` (never raises) when the name has no node.
        """
        ids = self._resolve_name(name)
        if not ids:
            return Explanation(symbol=name, resolved=False)

        node_id = ids[0]
        callers = self._call_graph.get_callers(node_id, depth=1)
        callees = self._call_graph.get_callees(node_id, depth=1)
        centrality = self.compute_centrality().get(node_id)
        if centrality is not None:
            score = centrality.score
            is_god = (centrality.in_degree + centrality.out_degree) >= god_node_threshold
        else:
            score = 0.0
            is_god = False
        return Explanation(
            symbol=name,
            resolved=True,
            node_id=node_id,
            callers=callers,
            callees=callees,
            god_node=is_god,
            centrality=score,
        )
