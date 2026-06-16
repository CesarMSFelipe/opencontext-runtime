"""Deterministic graph analysis over the persisted ``nodes``/``edges`` tables.

Computes in/out-degree centrality, flags high-centrality "god nodes" above a
configurable threshold, partitions nodes into modularity-scored communities
(deterministic label propagation), detects broker "hubs" by a deterministic
betweenness approximation, ranks nodes with a query-seeded personalized
PageRank, and exposes name-resolving ``path``/``explain`` queries built on
:class:`CallGraphAnalyzer`.

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
class Hub:
    """A broker node ranked by a deterministic betweenness approximation."""

    node_id: str
    name: str
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

    # ---- community detection ------------------------------------------

    def detect_communities(self, *, max_iterations: int = 100) -> dict[str, int]:
        """Partition nodes into modularity-scored communities.

        Uses deterministic, modularity-gain label propagation over the
        undirected call graph: each node adopts the neighbor label that most
        increases modularity, with ties broken on the smallest label. Unlike a
        plain connected-components partition, this splits dense clusters that are
        joined by a single bridge edge (the bridge does not justify merging two
        otherwise-cohesive groups). Nodes iterate in sorted order so the result
        is identical across repeated runs. Community ids are small ints assigned
        in ascending order of each community's smallest node id.
        """
        names = self._load_node_names()
        edges = self._load_edges()
        adjacency = self._undirected_adjacency(names, edges)
        labels = _modularity_label_propagation(names, adjacency, max_iterations=max_iterations)
        return _canonicalize_labels(names, labels)

    def modularity(self, partition: dict[str, int]) -> float:
        """Newman modularity of ``partition`` over the undirected call graph.

        Ranges roughly in ``[-0.5, 1.0]``; higher means denser intra-community
        connectivity than expected by chance. Returns ``0.0`` for an edgeless
        graph.
        """
        names = self._load_node_names()
        edges = self._load_edges()
        adjacency = self._undirected_adjacency(names, edges)
        return _modularity(adjacency, partition)

    # ---- hubs / personalized pagerank ---------------------------------

    def detect_hubs(self, *, top_k: int | None = None, min_score: float = 0.0) -> list[Hub]:
        """Detect broker "hub" nodes by a deterministic betweenness approximation.

        Computes unweighted shortest-path betweenness over the directed call
        graph (Brandes' algorithm, nodes processed in sorted order). Nodes that
        lie on many shortest paths between other nodes score highest. Returned in
        descending score (then node id), optionally truncated to ``top_k`` and
        filtered to ``score > min_score``. Deterministic for identical graphs.
        """
        names = self._load_node_names()
        edges = self._load_edges()
        adjacency = self._directed_adjacency(names, edges)
        betweenness = _betweenness_centrality(names, adjacency)
        hubs = [
            Hub(node_id=nid, name=names[nid], score=betweenness.get(nid, 0.0))
            for nid in sorted(names)
            if betweenness.get(nid, 0.0) > min_score
        ]
        hubs.sort(key=lambda h: (-h.score, h.node_id))
        if top_k is not None:
            hubs = hubs[:top_k]
        return hubs

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


# ---- community / modularity helpers (pure, deterministic) -------------------


def _modularity_label_propagation(
    names: dict[str, str],
    adjacency: dict[str, set[str]],
    *,
    max_iterations: int,
) -> dict[str, str]:
    """Label propagation that moves each node to the modularity-maximizing label.

    Each node starts in its own community (label == node id). On every sweep
    (nodes in sorted order) a node adopts the neighbor community whose adoption
    yields the greatest modularity gain, approximated locally as
    ``edges_to_community - (degree * community_degree) / (2m)``. Ties break on the
    smallest label. Converges when no node moves.
    """
    labels: dict[str, str] = {nid: nid for nid in sorted(names)}
    degree: dict[str, int] = {nid: len(adjacency[nid]) for nid in names}
    total_degree = sum(degree.values())
    if total_degree == 0:
        return labels
    two_m = float(total_degree)

    # Running sum of degrees per community label, kept in sync with moves.
    community_degree: dict[str, int] = defaultdict(int)
    for nid in names:
        community_degree[labels[nid]] += degree[nid]

    for _ in range(max_iterations):
        changed = False
        for node in sorted(names):
            neighbors = adjacency[node]
            if not neighbors:
                continue
            current = labels[node]
            links: dict[str, int] = defaultdict(int)
            for neighbor in neighbors:
                links[labels[neighbor]] += 1

            # Evaluate staying vs. moving; remove self-contribution so a node is
            # never compared against its own degree inside the target community.
            best_label = current
            best_gain = float("-inf")
            for label in sorted({current, *links}):
                self_degree = degree[node] if label == current else 0
                resident_degree = community_degree[label] - self_degree
                gain = links.get(label, 0) - (degree[node] * resident_degree) / two_m
                if gain > best_gain or (gain == best_gain and label < best_label):
                    best_gain = gain
                    best_label = label

            if best_label != current:
                community_degree[current] -= degree[node]
                community_degree[best_label] += degree[node]
                labels[node] = best_label
                changed = True
        if not changed:
            break
    return labels


def _canonicalize_labels(names: dict[str, str], labels: dict[str, str]) -> dict[str, int]:
    """Number communities by their smallest member id for stable, contiguous ids."""
    groups: dict[str, list[str]] = defaultdict(list)
    for node in sorted(names):
        groups[labels[node]].append(node)
    ordered = sorted(groups.values(), key=lambda members: min(members))
    partition: dict[str, int] = {}
    for community_id, members in enumerate(ordered):
        for node in members:
            partition[node] = community_id
    return partition


def _modularity(adjacency: dict[str, set[str]], partition: dict[str, int]) -> float:
    """Newman modularity ``Q`` for an undirected unweighted graph."""
    degree = {nid: len(neighbors) for nid, neighbors in adjacency.items()}
    two_m = float(sum(degree.values()))
    if two_m == 0.0:
        return 0.0

    intra_edges = 0.0
    for src, neighbors in adjacency.items():
        for dst in neighbors:
            if partition.get(src) == partition.get(dst):
                intra_edges += 1.0
    # Each undirected edge counted twice above; keep as 2*A_ij sum.

    degree_by_community: dict[int, int] = defaultdict(int)
    for nid, deg in degree.items():
        degree_by_community[partition.get(nid, -1)] += deg

    q = intra_edges / two_m
    for total_degree in degree_by_community.values():
        q -= (total_degree / two_m) ** 2
    return q


# ---- betweenness (Brandes, deterministic) ----------------------------------


def _betweenness_centrality(
    names: dict[str, str], adjacency: dict[str, set[str]]
) -> dict[str, float]:
    """Unweighted shortest-path betweenness over a directed graph.

    Brandes' algorithm with deterministic ordering (sources and adjacency walked
    in sorted order). Endpoints are excluded, matching the conventional
    definition, so pure source/sink nodes score ``0.0``.
    """
    betweenness: dict[str, float] = {nid: 0.0 for nid in names}
    nodes = sorted(names)
    out_links = {nid: sorted(adjacency[nid]) for nid in nodes}

    for source in nodes:
        stack: list[str] = []
        predecessors: dict[str, list[str]] = {nid: [] for nid in nodes}
        sigma: dict[str, float] = {nid: 0.0 for nid in nodes}
        distance: dict[str, int] = {nid: -1 for nid in nodes}
        sigma[source] = 1.0
        distance[source] = 0
        queue: deque[str] = deque([source])

        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in out_links[v]:
                if distance[w] < 0:
                    distance[w] = distance[v] + 1
                    queue.append(w)
                if distance[w] == distance[v] + 1:
                    sigma[w] += sigma[v]
                    predecessors[w].append(v)

        delta: dict[str, float] = {nid: 0.0 for nid in nodes}
        while stack:
            w = stack.pop()
            for v in predecessors[w]:
                if sigma[w] > 0.0:
                    delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != source:
                betweenness[w] += delta[w]

    return betweenness
