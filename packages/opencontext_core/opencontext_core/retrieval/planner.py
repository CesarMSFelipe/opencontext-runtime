"""Unified retrieval planner for manifest and graph-backed evidence."""

from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.context.planning.expansion import ContextItem as ExpansionItem
from opencontext_core.context.planning.expansion import ProgressiveExpander
from opencontext_core.graph.unified import UnifiedGraph
from opencontext_core.indexing.context_builder import ContextBuilder, ContextNode
from opencontext_core.models.context import ContextItem, ContextPriority
from opencontext_core.models.project import ProjectManifest
from opencontext_core.retrieval.contracts import (
    EvidenceItem,
    EvidencePlan,
    EvidenceRequest,
    FreshnessStatus,
    RetrievalSurface,
    TrustDecision,
    evidence_trace_id,
)
from opencontext_core.retrieval.retriever import ProjectRetriever
from opencontext_core.retrieval.scoring import (
    RetrievalWeights,
    compute_hybrid_score,
    identifier_quality_score,
    personalized_pagerank,
)
from opencontext_core.safety.redaction import SinkGuard


class RetrievalSource(Protocol):
    """A source that can produce context candidates for a query."""

    name: str

    def retrieve(self, query: str, limit: int) -> list[ContextItem]:
        """Return up to ``limit`` context candidates for ``query``."""


class ManifestRetrievalSource:
    """Retrieval source backed by the existing manifest retriever."""

    name = "manifest"

    def __init__(self, manifest: ProjectManifest) -> None:
        self._retriever = ProjectRetriever(manifest)

    def retrieve(self, query: str, limit: int) -> list[ContextItem]:
        """Return manifest candidates with source metadata attached."""

        return [
            _with_source_metadata(item, self.name)
            for item in self._retriever.retrieve(query, limit)
        ]


class GraphRetrievalSource:
    """Retrieval source backed by the native SQLite knowledge graph."""

    name = "graph"

    def __init__(self, db_path: str | Path, root: str | Path) -> None:
        self.db_path = Path(db_path)
        self.root = Path(root)

    def retrieve(self, query: str, limit: int) -> list[ContextItem]:
        """Return graph-derived candidates with provenance and freshness metadata."""

        if limit <= 0:
            return []
        builder = ContextBuilder(db_path=self.db_path)
        try:
            context = builder.build_context(
                task=query,
                max_nodes=limit,
                include_code=True,
                root=self.root,
            )
            return [
                _context_node_to_item(
                    node,
                    db_path=self.db_path,
                    query=query,
                )
                for node in context.nodes[:limit]
            ]
        finally:
            builder.close()


class VectorRetrievalSource:
    """Optional semantic retrieval source backed by a vector store.

    Embeds the query with the configured generator and returns nearest-neighbor
    candidates from the vector store as :class:`ContextItem`s. Attached only when
    ``config.embedding.enabled`` is true (see :meth:`RetrievalPlanner.from_config`),
    so the default-off config leaves planner behavior unchanged.
    """

    name = "vector"

    def __init__(self, store: Any, generator: Any, *, project_name: str = "") -> None:
        self._store = store
        self._generator = generator
        self._project_name = project_name

    def retrieve(self, query: str, limit: int) -> list[ContextItem]:
        """Return up to ``limit`` semantic candidates for ``query``."""

        if limit <= 0 or not query.strip():
            return []
        query_vector = _embed_query(self._generator, query)
        if not query_vector:
            return []
        # NOTE: the store's ``filters`` apply to each item's inner ``metadata``
        # dict, not the top-level ``project_name`` field, so project scoping is
        # done post-search against the stored record instead of via a store
        # filter (which would silently drop every match).
        try:
            results = self._store.search(query_vector, top_k=limit)
        except TypeError:
            results = self._store.search(query_vector, top_k=limit, filter=None)
        if self._project_name:
            results = [r for r in results if self._result_in_project(r)]
        return [_vector_result_to_item(result, query) for result in results]

    def _result_in_project(self, result: Any) -> bool:
        """Best-effort check that a search result belongs to this project."""

        getter = getattr(self._store, "get", None)
        if getter is None:
            return True
        try:
            record = getter(result.item_id)
        except Exception:
            return True
        if record is None:
            return True
        return getattr(record, "project_name", self._project_name) == self._project_name


class RetrievalPlanner:
    """Composes retrieval sources and returns deduplicated context candidates."""

    def __init__(
        self,
        manifest_or_sources: ProjectManifest | Sequence[RetrievalSource],
        *,
        graph_db_path: str | Path | None = None,
        memory_store: Any | None = None,
    ) -> None:
        if isinstance(manifest_or_sources, ProjectManifest):
            sources: list[RetrievalSource] = [ManifestRetrievalSource(manifest_or_sources)]
            if graph_db_path is not None:
                sources.append(GraphRetrievalSource(graph_db_path, manifest_or_sources.root))
            self.sources = sources
        else:
            self.sources = list(manifest_or_sources)
        # Retained for progressive graph expansion in plan(); a missing path
        # means expansion is a strict no-op (manifest/graph fallback unchanged).
        self.graph_db_path = Path(graph_db_path) if graph_db_path is not None else None
        self._memory_store = memory_store
        self.omissions: list[str] = []

    @classmethod
    def from_config(
        cls,
        manifest: ProjectManifest,
        config: Any,
        *,
        storage_path: str | Path,
        memory_store: Any | None = None,
    ) -> RetrievalPlanner:
        """Build a planner with config-gated graph + optional semantic sources.

        The vector (semantic) source is attached only when
        ``config.embedding.enabled`` is true; default off => identical behavior
        to the manifest(+graph) planner, so nothing changes unless vector data
        and the flag both exist.
        """

        storage = Path(storage_path)
        graph_db_path = storage / "context_graph.db"
        sources: list[RetrievalSource] = [ManifestRetrievalSource(manifest)]
        if graph_db_path.exists():
            sources.append(GraphRetrievalSource(graph_db_path, manifest.root))

        embedding = getattr(config, "embedding", None)
        if embedding is not None and getattr(embedding, "enabled", False):
            vector_source = _build_vector_source(config, storage, manifest.project_name)
            if vector_source is not None:
                sources.append(vector_source)

        planner = cls(sources, memory_store=memory_store)
        planner.graph_db_path = graph_db_path if graph_db_path.exists() else None
        return planner

    def retrieve(self, query: str, top_k: int) -> list[ContextItem]:
        """Retrieve candidates from all sources without letting additive sources block fallback."""

        if top_k <= 0:
            return []

        candidates: list[ContextItem] = []
        self.omissions = []
        for source in self.sources:
            try:
                candidates.extend(source.retrieve(query, top_k))
            except Exception:
                if source.name == ManifestRetrievalSource.name:
                    raise
                self.omissions.append(f"{source.name}_unavailable")
                continue

        deduped = _deduplicate(candidates)
        return _redact_selected(select_diverse(self.rank(deduped, query=query), top_k))

    def rank(
        self,
        items: list[ContextItem],
        *,
        memory_boost_map: dict[str, float] | None = None,
        graph_distance_map: dict[str, int] | None = None,
        query: str | None = None,
        focus_files: frozenset[str] | None = None,
    ) -> list[ContextItem]:
        """Order candidates by the hybrid score (semantic + provenance + graph +
        memory failure-boost + test-affinity + personalization, minus
        token/staleness penalties).

        ``memory_boost_map`` / ``graph_distance_map`` are optional signals the
        runtime can supply (from the memory store and call graph); they default to
        empty so the ranker is a pure, deterministic re-rank of the candidates.

        When ``query`` is provided, a personalized graph ranking signal is added:
        a query-seeded personalized PageRank over the candidates' call graph,
        blended with identifier-quality heuristics (query-mention boost, well-named
        boost, private/over-common downweighting, sqrt reference-count dampening).
        Omitting ``query`` leaves the ordering identical to the prior behavior.
        """

        mb = memory_boost_map or {}
        gd = graph_distance_map or {}
        weights = RetrievalWeights()
        personalization = (
            _personalization_map(items, query or "", focus_files)
            if (query or focus_files)
            else None
        )

        def _score(item: ContextItem) -> float:
            modified = item.metadata.get("modified_at")
            return compute_hybrid_score(
                candidate_id=item.id,
                candidate_source=item.source,
                candidate_source_type=item.source_type,
                candidate_source_trust=item.source_trust,
                candidate_modified_at=modified if isinstance(modified, str) else None,
                candidate_tokens=item.tokens,
                lexical_score=item.score,
                memory_boost_map=mb,
                graph_distance_map=gd,
                is_required=item.priority == ContextPriority.P0,
                is_test=_looks_like_test(item.source),
                weights=weights,
                personalization_map=personalization,
            )

        return sorted(items, key=lambda item: (-_score(item), item.tokens, item.id))

    def plan(self, request: EvidenceRequest, top_k: int) -> EvidencePlan:
        """Return a traceable evidence plan for a converged retrieval request.

        After the base manifest/graph retrieval, when a graph DB is available and
        ``request.expansion_rounds``/``graph_radius`` allow it, candidates are
        expanded via :class:`ProgressiveExpander` over a :class:`UnifiedGraph`
        built from the planner's graph DB. Expansion is additive and gated: with
        no graph DB it is a strict no-op and the existing fallback is untouched.
        The graph distance discovered by expansion (seeds=0, neighbors=1) is fed
        into :meth:`rank` so graph centrality actually shapes the ordering.
        """

        if top_k <= 0:
            base_items: list[ContextItem] = []
        else:
            base_items = []
            self.omissions = []
            for source in self.sources:
                try:
                    base_items.extend(source.retrieve(request.query, top_k))
                except Exception:
                    if source.name == ManifestRetrievalSource.name:
                        raise
                    self.omissions.append(f"{source.name}_unavailable")
                    continue
            base_items = _deduplicate(base_items)

        expanded_items, graph_distance_map = self._expand_with_graph(request, base_items)
        all_items = _deduplicate([*base_items, *expanded_items])
        ranked = self.rank(
            all_items,
            graph_distance_map=graph_distance_map or None,
            query=request.query,
            focus_files=_git_focus_files(request.root),
        )
        # Diversity-aware selection: maximize information per token by demoting
        # near-duplicates of already-chosen evidence before truncating to top_k.
        context_items = _redact_selected(select_diverse(ranked, top_k))

        evidence = [_context_item_to_evidence(item, request.surface) for item in context_items]
        fallback_actions = _fallback_actions_for(request, evidence)
        trust_decision = _trust_decision(request, evidence, fallback_actions)
        return EvidencePlan(
            request=request,
            evidence=evidence,
            fallback_actions=fallback_actions,
            trust_decision=trust_decision,
            trace_id=evidence_trace_id(request, [item.id for item in evidence]),
            omissions=list(self.omissions),
            source_surfaces=_source_surfaces(evidence, request.surface),
        )

    def _expand_with_graph(
        self, request: EvidenceRequest, seeds: list[ContextItem]
    ) -> tuple[list[ContextItem], dict[str, int]]:
        """Run ProgressiveExpander over a UnifiedGraph built from the graph DB.

        Returns ``(new_neighbor_items, graph_distance_map)``. Strict no-op (empty,
        empty) when there is no graph DB, no seeds, or expansion is disabled.
        """

        rounds = getattr(request, "expansion_rounds", 0)
        radius = getattr(request, "graph_radius", 1)
        if self.graph_db_path is None or not seeds or rounds <= 0:
            return [], {}
        if not Path(self.graph_db_path).exists():
            return [], {}

        from opencontext_core.indexing.graph_db import GraphDatabase
        from opencontext_core.memory.agent import NullAgentMemoryStore

        db = GraphDatabase(db_path=self.graph_db_path)
        try:
            # Map each seed to its graph node id when resolvable so the expander
            # traverses real call edges (else fall back to the seed's own id).
            id_to_seed: dict[str, ContextItem] = {}
            expansion_seeds: list[ExpansionItem] = []
            graph_distance_map: dict[str, int] = {}
            for item in seeds:
                node_id = _resolve_seed_node_id(db, item)
                key = node_id or item.id
                graph_distance_map[item.id] = 0
                if node_id:
                    graph_distance_map[node_id] = 0
                id_to_seed[key] = item
                expansion_seeds.append(ExpansionItem(id=key, source=item.source))

            if not expansion_seeds:
                return [], graph_distance_map

            memory = self._memory_store or NullAgentMemoryStore()
            graph = UnifiedGraph(graph_db=db, memory_store=memory)
            plan_obj = _ExpansionPlan(
                expansion_rounds=rounds,
                graph_radius=radius,
                include_memory=self._memory_store is not None,
            )
            contract = _ExpansionContract(required_symbols=[])
            result = ProgressiveExpander().expand(
                expansion_seeds, plan_obj, contract, graph=graph, memory=memory, round_num=1
            )

            new_items: list[ContextItem] = []
            seen_ids = set(graph_distance_map)
            for exp_item in result:
                if exp_item.id in id_to_seed or exp_item.id in seen_ids:
                    continue
                neighbor = _expansion_item_to_context_item(db, exp_item)
                if neighbor is None:
                    continue
                graph_distance_map[neighbor.id] = 1
                seen_ids.add(exp_item.id)
                new_items.append(neighbor)
            return new_items, graph_distance_map
        except Exception:
            # Expansion is best-effort; never break the base retrieval contract.
            self.omissions.append("graph_expansion_unavailable")
            return [], {}
        finally:
            db.close()


def _looks_like_test(source: str) -> bool:
    base = source.rsplit("/", 1)[-1].lower()
    return base.startswith("test_") or base.endswith("_test.py") or "/tests/" in source.lower()


# ---- personalized graph ranking ---------------------------------------------


def _query_terms(query: str) -> set[str]:
    """Lowercase alphanumeric tokens of ``query``, length >= 2."""
    tokens: set[str] = set()
    word = ""
    for ch in query:
        if ch.isalnum():
            word += ch
        else:
            if len(word) >= 2:
                tokens.add(word.lower())
            word = ""
    if len(word) >= 2:
        tokens.add(word.lower())
    return tokens


def _candidate_name(item: ContextItem) -> str:
    """Best-effort symbol name for a candidate from its metadata, else its source."""
    retrieval = item.metadata.get("retrieval")
    if isinstance(retrieval, dict):
        node = retrieval.get("node")
        if isinstance(node, str) and node:
            return node
    source = item.source.rsplit("/", 1)[-1]
    return source.split(":", 1)[0].removesuffix(".py")


def _candidate_relationships(item: ContextItem) -> list[str]:
    """Related symbol names declared in a candidate's graph metadata."""
    out: list[str] = []
    retrieval = item.metadata.get("retrieval")
    if isinstance(retrieval, dict):
        rels = retrieval.get("relationships")
        if isinstance(rels, list):
            out.extend(str(r) for r in rels)
    provenance = item.metadata.get("graph_provenance")
    if isinstance(provenance, dict):
        rels = provenance.get("relationships")
        if isinstance(rels, list):
            out.extend(str(r) for r in rels)
    return out


def _candidate_file(item: ContextItem) -> str:
    """The repo-relative file path a candidate came from (drops any :line:name)."""
    return item.source.split(":", 1)[0]


def _git_focus_files(root: Path | None) -> frozenset[str]:
    """Repo-relative files recently changed in git — the developer's working set.

    Best-effort: returns an empty set when git is unavailable or the path is not a
    repo, so retrieval is unaffected outside a git working tree.
    """
    if root is None:
        return frozenset()
    try:
        from opencontext_core.indexing.git_context import GitContextProvider

        files: set[str] = set()
        for diff in GitContextProvider(root).get_recent_changes(days=7):
            files.update(diff.files_changed)
        return frozenset(files)
    except Exception:
        return frozenset()


def _personalization_map(
    items: list[ContextItem], query: str, focus_files: frozenset[str] | None = None
) -> dict[str, float]:
    """Build a per-candidate personalization signal in ``[0, 1]``.

    Combines a query-seeded personalized PageRank over the candidates' call graph
    with per-identifier quality heuristics, so candidates that are both
    well-named/query-mentioned and graph-central rise. When ``focus_files`` is
    given (e.g. the git working set), candidates from those files also seed the
    PageRank, so the map adapts to what the developer is actually changing right
    now. Pure and deterministic for a fixed input.
    """
    terms = _query_terms(query)
    if not items:
        return {}

    names = {item.id: _candidate_name(item) for item in items}
    name_to_ids: dict[str, list[str]] = defaultdict(list)
    for item_id, name in names.items():
        name_to_ids[name].append(item_id)

    # Reference counts: how often each candidate's name is referenced by peers
    # (used to dampen over-common symbols via sqrt in the quality heuristic).
    reference_count: dict[str, int] = defaultdict(int)
    adjacency: dict[str, set[str]] = {item.id: set() for item in items}
    for item in items:
        for rel in _candidate_relationships(item):
            for target_id in name_to_ids.get(rel, ()):
                if target_id != item.id:
                    adjacency[item.id].add(target_id)
                    adjacency[target_id].add(item.id)
                    reference_count[target_id] += 1

    quality = {
        item.id: identifier_quality_score(
            names[item.id], terms, reference_count=reference_count.get(item.id, 0)
        )
        for item in items
    }

    seeds = {item_id for item_id, name in names.items() if _query_terms(name) & terms}
    if focus_files:
        seeds.update(item.id for item in items if _candidate_file(item) in focus_files)
    pagerank = personalized_pagerank(adjacency, seeds)
    max_pr = max(pagerank.values(), default=0.0)

    blended: dict[str, float] = {}
    for item in items:
        pr = (pagerank.get(item.id, 0.0) / max_pr) if max_pr > 0.0 else 0.0
        # Weight identifier quality (carries the direct query-mention signal)
        # slightly above raw graph mass so a tie on the graph still surfaces the
        # query-relevant symbol.
        blended[item.id] = max(0.0, min(1.0, 0.6 * quality[item.id] + 0.4 * pr))
    return blended


def _with_source_metadata(item: ContextItem, source_name: str) -> ContextItem:
    metadata = {**item.metadata, "retrieval_source": source_name}
    return item.model_copy(update={"metadata": metadata})


def _context_item_to_evidence(item: ContextItem, surface: RetrievalSurface) -> EvidenceItem:
    freshness = _freshness_from_metadata(item.metadata)
    provenance = {
        **item.metadata,
        "source": item.source,
        "source_type": item.source_type,
        "priority": item.priority.name,
    }
    return EvidenceItem(
        id=item.id,
        content=item.content,
        source=item.source,
        source_type=item.source_type,
        provenance=provenance,
        confidence=max(0.0, min(1.0, item.score if item.score > 0 else item.source_trust)),
        freshness=freshness,
        surface=surface,
        tokens=item.tokens,
        protected=bool(item.metadata.get("protected", False)),
        classification=item.classification,
    )


def _freshness_from_metadata(metadata: dict[str, object]) -> FreshnessStatus:
    value = metadata.get("freshness", FreshnessStatus.CURRENT.value)
    try:
        return FreshnessStatus(str(value))
    except ValueError:
        return FreshnessStatus.UNKNOWN


def _fallback_actions_for(request: EvidenceRequest, evidence: list[EvidenceItem]) -> list[str]:
    if request.risk_level.lower() != "high":
        return []
    insufficient = {
        FreshnessStatus.STALE,
        FreshnessStatus.UNKNOWN,
        FreshnessStatus.UNAVAILABLE,
    }
    return [f"read_source:{item.source}" for item in evidence if item.freshness in insufficient]


def _trust_decision(
    request: EvidenceRequest,
    evidence: list[EvidenceItem],
    fallback_actions: list[str],
) -> TrustDecision:
    if not evidence:
        return TrustDecision(status="insufficient", reason="no evidence available")
    if request.risk_level.lower() == "high" and fallback_actions:
        return TrustDecision(
            status="insufficient",
            reason="high-risk evidence requires explicit source fallback",
        )
    return TrustDecision(status="sufficient", reason="evidence freshness is acceptable")


def _source_surfaces(
    evidence: list[EvidenceItem],
    default_surface: RetrievalSurface,
) -> list[RetrievalSurface]:
    surfaces = list(dict.fromkeys(item.surface for item in evidence))
    return surfaces or [default_surface]


def _context_node_to_item(node: ContextNode, *, db_path: Path, query: str) -> ContextItem:
    content = _render_node_content(node)
    metadata = {
        "retrieval_source": "graph",
        "retrieval": {
            "query": query,
            "node": node.name,
            "kind": node.kind,
            "relationships": list(node.relationships),
        },
        "retrieval_rationale": _graph_rationale(node),
        "source_type": "graph",
        "freshness": "unknown",
        "graph_provenance": {
            "db_path": str(db_path),
            "file_path": node.file_path,
            "line": node.line,
            "relationships": list(node.relationships),
        },
        "symbol_kind": node.kind,
    }
    return ContextItem(
        id=f"graph:{node.file_path}:{node.line}:{node.name}",
        content=content,
        source=f"{node.file_path}:{node.line}",
        source_type="graph_symbol",
        priority=ContextPriority.P1,
        tokens=estimate_tokens(content),
        score=max(node.relevance_score, 0.0),
        metadata=metadata,
        trusted=True,
        source_trust=0.8,
    )


def _render_node_content(node: ContextNode) -> str:
    header = f"{node.kind} {node.name} in {node.file_path}:{node.line}"
    if node.source_code:
        return f"{header}\n{node.source_code}".strip()
    return header


def _graph_rationale(node: ContextNode) -> list[str]:
    rationale = [
        "source_type:graph",
        f"symbol_kind:{node.kind}",
        f"file:{node.file_path}",
    ]
    rationale.extend(f"relationship:{relationship}" for relationship in node.relationships)
    return rationale


def _deduplicate(items: list[ContextItem]) -> list[ContextItem]:
    by_id: dict[str, ContextItem] = {}
    for item in items:
        current = by_id.get(item.id)
        if current is None or item.score > current.score:
            by_id[item.id] = item
    return list(by_id.values())


# Relevance weight in MMR selection: high so the most relevant item still leads,
# but redundant near-duplicates of it are demoted in favor of new information.
_MMR_LAMBDA = 0.7
_WORD_RE = re.compile(r"[a-z0-9_]+")


def _content_tokens(text: str) -> frozenset[str]:
    return frozenset(_WORD_RE.findall((text or "").lower()))


def _token_jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 0.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _redact_selected(items: list[ContextItem]) -> list[ContextItem]:
    """Redact secrets/PII in the SELECTED items just before they become evidence.

    Candidates are read raw for speed; redaction is applied here, over the small
    delivered set, so every item that reaches the agent is clean while the
    expensive secret/PII scan never runs over the whole candidate corpus.
    """
    guard = SinkGuard()
    out: list[ContextItem] = []
    for item in items:
        redacted, changed = guard.redact(item.content)
        if changed or redacted != item.content:
            out.append(
                item.model_copy(
                    update={"content": redacted, "metadata": {**item.metadata, "redacted": True}}
                )
            )
        else:
            out.append(item)
    return out


def select_diverse(
    items: list[ContextItem], k: int, *, lam: float = _MMR_LAMBDA
) -> list[ContextItem]:
    """Pick ``k`` items maximizing relevance minus redundancy (greedy MMR).

    ``items`` must already be relevance-ranked. The first (most relevant) item is
    always kept; each subsequent pick maximizes ``lam*relevance - (1-lam)*maxSim``
    where similarity is token-set Jaccard against the already-selected items, so
    the pack covers distinct facets instead of N near-duplicates of one hot symbol.
    Deterministic: ties resolve to the earlier (higher-ranked) candidate.
    """
    if k <= 0 or len(items) <= 1:
        return items[: max(k, 0)]
    if len(items) <= k:
        return items  # nothing to trade off; keep all

    # Normalize relevance by the max score (proportional, scale-independent) rather
    # than min-max — min-max amplifies tiny score gaps into the full [0,1] range and
    # would let a near-duplicate beat a distinct item of nearly equal relevance.
    hi = max(it.score for it in items)
    norm = hi if hi > 0 else 1.0
    tokens = {id(it): _content_tokens(it.content) for it in items}

    remaining = list(items)
    selected = [remaining.pop(0)]
    while remaining and len(selected) < k:
        best = None
        best_val = None
        for cand in remaining:
            rel = max(cand.score, 0.0) / norm
            sim = max(
                (_token_jaccard(tokens[id(cand)], tokens[id(s)]) for s in selected),
                default=0.0,
            )
            val = lam * rel - (1.0 - lam) * sim
            if best_val is None or val > best_val:
                best, best_val = cand, val
        selected.append(best)  # type: ignore[arg-type]
        remaining.remove(best)  # type: ignore[arg-type]
    return selected


# ---- progressive graph expansion helpers ------------------------------------


@dataclass
class _ExpansionPlan:
    """Minimal plan shape consumed by ProgressiveExpander.expand."""

    expansion_rounds: int
    graph_radius: int
    include_memory: bool = False


@dataclass
class _ExpansionContract:
    """Minimal contract shape consumed by ProgressiveExpander.expand."""

    required_symbols: list[str]


def _resolve_seed_node_id(db: Any, item: ContextItem) -> str | None:
    """Resolve a retrieved candidate to a stable graph node id, if it maps to one.

    Tries (in order): the item id used directly as a node id; the
    ``graph_provenance``/``retrieval`` metadata (file_path + line + node name);
    and finally a name lookup. Returns ``None`` when nothing resolves so the
    expander falls back to the item's own id.
    """

    conn = db._connect()
    # 1) Item id is itself a stable node id.
    row = conn.execute("SELECT id FROM nodes WHERE id = ?", (item.id,)).fetchone()
    if row is not None:
        return str(row["id"])

    # 2) Graph-sourced items carry file_path/line/name provenance.
    provenance = item.metadata.get("graph_provenance")
    retrieval = item.metadata.get("retrieval")
    name = None
    file_path = None
    line = None
    if isinstance(retrieval, dict):
        name = retrieval.get("node")
    if isinstance(provenance, dict):
        file_path = provenance.get("file_path")
        line = provenance.get("line")
    if name and file_path is not None and line is not None:
        row = conn.execute(
            "SELECT id FROM nodes WHERE name = ? AND file_path = ? AND line = ?",
            (name, file_path, line),
        ).fetchone()
        if row is not None:
            return str(row["id"])

    # 3) Last resort: unique name match.
    if name:
        rows = conn.execute("SELECT id FROM nodes WHERE name = ?", (name,)).fetchall()
        if len(rows) == 1:
            return str(rows[0]["id"])
    return None


def _expansion_item_to_context_item(db: Any, exp_item: Any) -> ContextItem | None:
    """Convert an expander neighbor (by node id) into an additive ContextItem."""

    conn = db._connect()
    row = conn.execute(
        "SELECT id, name, kind, file_path, line, signature, docstring FROM nodes WHERE id = ?",
        (exp_item.id,),
    ).fetchone()
    if row is None:
        return None
    name = row["name"] or ""
    kind = row["kind"] or "symbol"
    file_path = row["file_path"] or ""
    line = row["line"] if row["line"] is not None else 0
    signature = row["signature"] or ""
    header = f"{kind} {name} in {file_path}:{line}"
    content = f"{header}\n{signature}".strip() if signature else header
    return ContextItem(
        id=f"graph:{file_path}:{line}:{name}",
        content=content,
        source=f"{file_path}:{line}",
        source_type="graph_symbol",
        priority=ContextPriority.P2,
        tokens=estimate_tokens(content),
        score=0.0,
        metadata={
            "retrieval_source": "graph_expansion",
            "retrieval_rationale": ["source_type:graph_expansion", f"symbol_kind:{kind}"],
            "source_type": "graph",
            "freshness": "unknown",
            "graph_provenance": {"file_path": file_path, "line": line, "node_id": str(row["id"])},
            "symbol_kind": kind,
        },
        trusted=True,
        source_trust=0.7,
    )


# ---- semantic (vector) source helpers ---------------------------------------


def _embed_query(generator: Any, query: str) -> list[float]:
    """Embed a single query string, bridging the async generator API to sync.

    ``RetrievalSource.retrieve`` is synchronous, so we drive the async embedder
    on a private loop. Returns an empty list on any failure so the planner
    treats it as "no semantic candidates" rather than raising.
    """

    try:
        vectors = asyncio.run(generator.embed([query]))
    except RuntimeError:
        # Already inside a running loop: use a dedicated loop instead.
        loop = asyncio.new_event_loop()
        try:
            vectors = loop.run_until_complete(generator.embed([query]))
        finally:
            loop.close()
    except Exception:
        return []
    return list(vectors[0]) if vectors else []


def _vector_result_to_item(result: Any, query: str) -> ContextItem:
    """Convert a VectorSearchResult into a planner ContextItem."""

    content = result.content or ""
    item_id = result.item_id or result.source_path or "vector"
    score = max(0.0, min(1.0, float(result.score)))
    metadata = {
        "retrieval_source": "vector",
        "retrieval_rationale": ["source_type:vector", f"score:{score:.4f}"],
        "source_type": "vector",
        "freshness": "unknown",
        "vector_provenance": {
            "query": query,
            "source_path": result.source_path,
            "item_type": result.source_type,
        },
    }
    if isinstance(getattr(result, "metadata", None), dict):
        metadata["vector_metadata"] = result.metadata
    return ContextItem(
        id=str(item_id),
        content=content,
        source=result.source_path or str(item_id),
        source_type="vector",
        priority=ContextPriority.P2,
        tokens=estimate_tokens(content) if content else 0,
        score=score,
        metadata=metadata,
        trusted=False,
        source_trust=0.6,
    )


def _build_vector_source(
    config: Any, storage_path: Path, project_name: str
) -> VectorRetrievalSource | None:
    """Construct a VectorRetrievalSource from config, or None if unavailable."""

    try:
        from opencontext_core.embeddings.generators import create_generator
        from opencontext_core.embeddings.stores import LocalVectorStore

        generator = create_generator(config)
        store = LocalVectorStore(storage_path)
    except Exception:
        return None
    return VectorRetrievalSource(store, generator, project_name=project_name)
