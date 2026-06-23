"""Deterministic graph analysis over the persisted ``nodes``/``edges`` tables.

Computes in/out-degree centrality, flags high-centrality "god nodes" above a
configurable threshold, detects dependency/call cycles (Tarjan SCC), ranks nodes
with a query-seeded personalized PageRank, and exposes name-resolving
``path``/``explain`` queries built on :class:`CallGraphAnalyzer`.

Zero new hard dependencies: everything runs on the standard library and the
existing :class:`GraphDatabase` SQLite connection. ``networkx`` is used only if
it is already importable (purely optional); the pure-Python path is the default
and is the one exercised by the tests. Results are reproducible for identical
graph content because every traversal iterates in a deterministic, sorted order.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from opencontext_core.indexing.call_graph import CallGraphAnalyzer, PathResult
from opencontext_core.indexing.graph_db import GraphDatabase
from opencontext_core.retrieval.scoring import personalized_pagerank


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


@dataclass(frozen=True)
class Cycle:
    """A strongly-connected component (a dependency/call cycle).

    ``nodes`` is the SORTED tuple of member ids (call cycles) or file paths
    (import cycles), so the value is stable across runs; ``size`` is its length.
    A self-loop yields a one-member cycle.
    """

    nodes: tuple[str, ...]  # member ids (or paths), sorted
    size: int


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

    def _undirected_adjacency(
        self, names: dict[str, str], edges: list[tuple[str, str]]
    ) -> dict[str, set[str]]:
        """Symmetric adjacency (no self-loops) restricted to known nodes."""
        adjacency: dict[str, set[str]] = {nid: set() for nid in names}
        for src, dst in edges:
            if src in adjacency and dst in adjacency and src != dst:
                adjacency[src].add(dst)
                adjacency[dst].add(src)
        return adjacency

    def _directed_adjacency(
        self, names: dict[str, str], edges: list[tuple[str, str]]
    ) -> dict[str, set[str]]:
        """Directed adjacency (source -> targets) restricted to known nodes."""
        adjacency: dict[str, set[str]] = {nid: set() for nid in names}
        for src, dst in edges:
            if src in adjacency and dst in adjacency and src != dst:
                adjacency[src].add(dst)
        return adjacency

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

    # ---- cycles (Tarjan SCC) ------------------------------------------

    def detect_cycles(self, adjacency: dict[str, set[str]] | None = None) -> list[Cycle]:
        """Detect dependency/call cycles via Tarjan strongly-connected components.

        When ``adjacency`` is ``None`` the adjacency is built from the persisted
        call graph (``_directed_adjacency`` over ``self._edge_kinds``), so the
        result is the set of *call* cycles. When ``adjacency`` is supplied (a
        path-keyed directed graph, e.g. file-level import edges from
        :class:`DependencyGraphBuilder`), Tarjan runs over it directly so the
        result is the set of *import* cycles.

        Returns only SCCs that represent a real cycle: a component of size > 1,
        or a single node with a self-loop. Each :class:`Cycle` carries its member
        ids sorted, and the returned list is sorted by that member tuple, so the
        output is fully deterministic for identical graph content. The
        implementation is an iterative (explicit-stack) Tarjan so a deep graph
        cannot blow the Python recursion limit; it uses only the standard library.
        """
        if adjacency is None:
            names = self._load_node_names()
            edges = self._load_edges()
            adjacency = self._directed_adjacency(names, edges)
        return _tarjan_scc(adjacency)

    # ---- personalized pagerank ----------------------------------------

    def personalized_pagerank(
        self,
        *,
        seed_names: list[str] | None = None,
        seed_ids: list[str] | None = None,
        damping: float = 0.85,
    ) -> dict[str, float]:
        """Personalized PageRank over the call graph (undirected), keyed by node id.

        Edges are treated as undirected because for relevance ranking a symbol's
        callers are as pertinent as its callees, so the random surfer should be
        able to reach both. Seeds are the union of ``seed_ids`` and every node id
        resolved from ``seed_names``; restart mass concentrates on them so their
        graph neighborhood is lifted. With no resolvable seeds the restart
        distribution is uniform (classic PageRank). Deterministic for identical
        graph content.
        """
        names = self._load_node_names()
        edges = self._load_edges()
        adjacency = self._undirected_adjacency(names, edges)
        seeds: set[str] = set(seed_ids or [])
        for name in seed_names or []:
            seeds.update(self._resolve_name(name))
        return personalized_pagerank(adjacency, seeds, damping=damping)

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


# ---- cycles (Tarjan SCC, iterative, deterministic) --------------------------


def _tarjan_scc(adjacency: dict[str, set[str]]) -> list[Cycle]:
    """Iterative Tarjan SCC returning only cycle components, sorted deterministically.

    A component is a cycle when it has more than one member, or it is a single
    node that links to itself (a self-loop). Neighbors are visited in sorted
    order and the returned list is sorted by each component's sorted member
    tuple, so identical input always yields identical output. Nodes referenced
    only as edge targets (not keys) are tolerated — they are treated as having no
    outgoing edges.
    """
    index_counter = 0
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    stack: list[str] = []
    components: list[list[str]] = []

    nodes = sorted(adjacency)

    def successors(node: str) -> list[str]:
        # Sorted for determinism; tolerate target-only nodes (absent as keys).
        return sorted(adjacency.get(node, ()))

    for start in nodes:
        if start in indices:
            continue
        # Explicit DFS stack of (node, iterator-position) frames.
        work: list[tuple[str, int]] = [(start, 0)]
        succ_cache: dict[str, list[str]] = {}
        while work:
            node, child_idx = work[-1]
            if child_idx == 0:
                indices[node] = index_counter
                lowlink[node] = index_counter
                index_counter += 1
                stack.append(node)
                on_stack[node] = True
                succ_cache[node] = successors(node)

            succ = succ_cache[node]
            if child_idx < len(succ):
                work[-1] = (node, child_idx + 1)
                child = succ[child_idx]
                if child not in indices:
                    work.append((child, 0))
                elif on_stack.get(child):
                    lowlink[node] = min(lowlink[node], indices[child])
                continue

            # All successors processed: if root of an SCC, pop the component.
            if lowlink[node] == indices[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack[member] = False
                    component.append(member)
                    if member == node:
                        break
                components.append(component)

            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])

    cycles: list[Cycle] = []
    for component in components:
        if len(component) > 1:
            members = tuple(sorted(component))
            cycles.append(Cycle(nodes=members, size=len(members)))
        else:
            node = component[0]
            if node in adjacency.get(node, set()):  # self-loop
                cycles.append(Cycle(nodes=(node,), size=1))
    cycles.sort(key=lambda c: c.nodes)
    return cycles
