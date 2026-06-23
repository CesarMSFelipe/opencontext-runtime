"""Architecture analysis: graph structure -> quality :class:`Finding` objects.

``ArchitectureAnalyzer`` orchestrates four deterministic, model-free passes over
the project's knowledge graph and turns each into normalized
``Finding(category='architecture')`` objects:

* **cycles** — FILE-level import cycles. The persisted ``edges`` table holds only
  ``calls`` edges (there are *no* import edges in the DB), so the import
  adjacency is rebuilt in-memory from :class:`DependencyGraphBuilder` and fed to
  the SOLE Tarjan implementation, :meth:`GraphAnalyzer.detect_cycles`. Call-level
  cycles (over ``edge_kinds``) are available as a secondary signal.
* **god files** — files whose aggregated fan-in (or LOC) crosses a threshold,
  derived from :meth:`GraphAnalyzer.compute_centrality` rolled up to the file via
  each node's ``file_path``.
* **boundaries** — declared-layer dependency rules, checked by glob-matching each
  in-memory dependency edge's endpoints to a layer.
* **complexity** — per-symbol cyclomatic complexity via the parser's
  :meth:`TreeSitterParser.cyclomatic_complexity` (Python first; other languages
  are explicitly *skipped*, never silently scored).

This module never decides pass/fail — it only produces metrics + findings. The
``QualityEvaluator`` owns mode/severity/ratchet logic. Everything here is
deterministic (sorted iteration, integer signals) and makes zero model calls.
"""

from __future__ import annotations

import fnmatch
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opencontext_core.indexing.dependency_graph import DependencyGraphBuilder
from opencontext_core.indexing.graph_analysis import Centrality, GraphAnalyzer
from opencontext_core.indexing.graph_db import GraphDatabase
from opencontext_core.indexing.scanner import ScannedFile
from opencontext_core.indexing.tree_sitter_parser import TreeSitterParser
from opencontext_core.quality.ci_checks import CheckSeverity
from opencontext_core.quality.models import Finding, QualityMetrics
from opencontext_core.quality.rules import ArchitectureRules, BoundaryRule, LayerRule

# Near-duplicate (clone) detection knobs. Deterministic, in-process only.
# A function body is tokenized (split on non-alphanumeric), windowed into
# fixed-width K-token shingles, and each shingle hashed. Two functions are a
# near-duplicate when their shared-shingle count clears the configured
# ``min_duplicate_tokens`` AND their Jaccard overlap is at least ``_DUP_OVERLAP``.
_DUP_SHINGLE = 5  # shingle window width (tokens per shingle)
_DUP_OVERLAP = 0.85  # Jaccard-style overlap ratio required to flag a pair


def _gini_bp(values: list[int]) -> int:
    """Gini coefficient of a non-negative distribution, in basis points (0..10000).

    0 = perfectly even (every file the same size); 10000 = maximally concentrated
    (one file holds it all). Standard mean-absolute-difference Gini over the
    ascending-sorted positive values. Returns 0 for fewer than two non-empty
    files or a zero total — there is no distribution signal to report.
    """
    xs = sorted(v for v in values if v > 0)
    n = len(xs)
    total = sum(xs)
    if n < 2 or total == 0:
        return 0
    weighted = sum(i * x for i, x in enumerate(xs, start=1))  # i is 1-based
    gini = (2 * weighted) / (n * total) - (n + 1) / n
    return max(0, min(10000, round(gini * 10000)))


@dataclass(frozen=True)
class GodFile:
    """A file flagged as a god-file (excessive fan-in or size)."""

    file: str
    in_degree: int
    out_degree: int
    loc: int


@dataclass(frozen=True)
class BoundaryViolation:
    """A dependency edge that crosses a disallowed layer boundary."""

    source_file: str
    target_file: str
    from_layer: str
    to_layer: str
    reason: str


@dataclass(frozen=True)
class ComplexityFinding:
    """A single over-threshold cyclomatic-complexity hotspot."""

    file: str
    symbol: str
    complexity: int
    line: int


@dataclass(frozen=True)
class DuplicationFinding:
    """A near-duplicate (clone) pair of functions, ordered canonically.

    The pair is canonically ordered so ``(file_a, symbol_a) <= (file_b,
    symbol_b)`` — this makes the composite pair fingerprint (used as the
    ``Finding.symbol``) stable and unique per distinct clone, exactly like the
    per-cycle fingerprint. ``tokens`` is the size of the shared shingle overlap.
    """

    file_a: str
    symbol_a: str
    line_a: int
    file_b: str
    symbol_b: str
    line_b: int
    tokens: int


@dataclass(frozen=True)
class NestingFinding:
    """A single over-threshold CODE block-nesting hotspot (not directory depth)."""

    file: str
    symbol: str
    depth: int
    line: int


@dataclass(frozen=True)
class _DupFunction:
    """Internal: one function's clone-detection fingerprint (shingle set)."""

    file: str
    symbol: str
    line: int
    shingles: frozenset[tuple[str, ...]]


@dataclass(frozen=True)
class ArchitectureReport:
    """The aggregate result of an architecture pass.

    ``findings`` is the normalized list every consumer reads; the typed tuples
    (``cycles``/``god_files``/…) are the structured detail behind them; ``metrics``
    feeds the health score; ``skipped`` records any pass that could not run (e.g.
    complexity when tree-sitter is unavailable), so the gate degrades honestly.
    """

    cycles: tuple[tuple[str, ...], ...]
    god_files: tuple[GodFile, ...]
    boundary_violations: tuple[BoundaryViolation, ...]
    complexity: tuple[ComplexityFinding, ...]
    metrics: QualityMetrics
    findings: tuple[Finding, ...]
    skipped: tuple[str, ...] = ()
    duplication: tuple[DuplicationFinding, ...] = ()
    nesting: tuple[NestingFinding, ...] = ()


class ArchitectureAnalyzer:
    """Deterministic architecture analysis over one project's knowledge graph."""

    def __init__(
        self,
        db_path: Path,
        *,
        scanned_files: list[ScannedFile] | None = None,
        edge_kinds: tuple[str, ...] = ("calls",),
    ) -> None:
        """Bind to the graph DB and (optionally) the scanned source.

        ``db_path`` is ``<root>/.storage/opencontext/context_graph.db``.
        ``scanned_files`` supplies the file-level import graph (for cycles), the
        per-file LOC (for god-files), and the source content (for complexity); if
        it is ``None`` those passes that *need* source degrade honestly — import
        cycles are skipped (recorded), while the call-graph passes still run off
        the DB.
        """
        self.db_path = Path(db_path)
        self.scanned_files = scanned_files
        self.edge_kinds = edge_kinds
        self._parser = TreeSitterParser()
        # Per-instance caches. A single ``analyze()`` used to do TWO full
        # ``DependencyGraphBuilder().build(self.scanned_files)`` calls (once
        # from ``detect_cycles`` and again from ``detect_boundaries``) and a
        # fresh sqlite centrality sweep for the god-file roll-up + the metrics
        # roll-up. Caching trims that to one build + one centrality sweep per
        # analyzer lifetime, which is bounded by the harness gate's call site.
        # NOTE: the cache names MUST NOT collide with method names; in CPython
        # an instance attribute shadows its same-named method on lookup, so
        # ``self._centrality()`` was previously returning ``None()`` (the
        # initial ``None`` cached the attribute, hiding the method). The
        # ``_cache`` suffix below side-steps that.
        self._dep_graph_cache: Any | None = None
        self._centrality_cache: dict[str, Centrality] | None = None
        self._node_files_cache: dict[str, str] | None = None

    # -- orchestration ----------------------------------------------------- #

    def analyze(
        self,
        rules: ArchitectureRules,
        *,
        changed_files: list[str] | None = None,
    ) -> ArchitectureReport:
        """Run all four passes and normalize the results into one report.

        Cycles and coupling are computed over the whole graph (a cycle is a
        whole-graph property), but symbol-scoped findings (god-files, complexity,
        boundary violations) are filtered to ``changed_files`` when given so the
        in-loop check reports only what the change touched. A cycle is only
        *reported* when one of its members is in scope (when scope is given).
        """
        scope = self._normalize_scope(changed_files)

        cycles = self.detect_cycles(rules)
        god_files = self.detect_god_files(rules)
        boundary_violations = self.detect_boundaries(rules.layers, rules.boundaries)
        complexity, complexity_skipped = self._compute_complexity(rules, scope=scope)
        duplication, dup_skipped = self._compute_duplication(rules, scope=scope)
        nesting, nesting_skipped = self._compute_nesting(rules, scope=scope)

        skipped: list[str] = list(complexity_skipped)
        skipped.extend(dup_skipped)
        skipped.extend(nesting_skipped)
        if self.scanned_files is None:
            skipped.append("max_cycles:no-source-scanned")

        # Scope filtering for the symbol-scoped passes.
        if scope is not None:
            god_files = tuple(g for g in god_files if g.file in scope)
            boundary_violations = tuple(
                b for b in boundary_violations if b.source_file in scope or b.target_file in scope
            )
            reported_cycles = tuple(c for c in cycles if any(member in scope for member in c))
        else:
            reported_cycles = cycles

        findings = self._build_findings(
            rules, reported_cycles, god_files, boundary_violations, complexity, duplication, nesting
        )

        metrics = self._build_metrics(
            cycles, god_files, complexity, boundary_violations, duplication, nesting, scope=scope
        )

        return ArchitectureReport(
            cycles=reported_cycles,
            god_files=god_files,
            boundary_violations=boundary_violations,
            complexity=complexity,
            metrics=metrics,
            findings=findings,
            skipped=tuple(dict.fromkeys(skipped)),
            duplication=duplication,
            nesting=nesting,
        )

    # -- individual passes ------------------------------------------------- #

    def detect_cycles(self, rules: ArchitectureRules) -> tuple[tuple[str, ...], ...]:
        """File-level import cycles (the headline cycle signal).

        Builds the import adjacency in-memory from
        :meth:`DependencyGraphBuilder.build` (the DB has no import edges) and runs
        the shared Tarjan SCC via :meth:`GraphAnalyzer.detect_cycles`. Returns the
        sorted member tuple of every cycle. When no source was scanned this
        returns ``()`` (the absence is recorded by :meth:`analyze` as skipped, not
        a clean pass).
        """
        if not self.scanned_files:
            return ()
        adjacency = self._import_adjacency()
        analyzer = self._graph_analyzer()
        try:
            cycles = analyzer.detect_cycles(adjacency)
        finally:
            analyzer.close()
        return tuple(cycle.nodes for cycle in cycles)

    def detect_call_cycles(self) -> tuple[tuple[str, ...], ...]:
        """Secondary signal: cycles over the persisted call graph (``edge_kinds``).

        Distinct from :meth:`detect_cycles` (which is FILE-level import cycles);
        this runs Tarjan over the in-DB call edges and is exposed so callers/tests
        can use it, but it is not the headline cycle metric. Tolerant of a missing
        DB (returns ``()``), mirroring the other call-graph passes.
        """
        if not self.db_path.exists():
            return ()
        analyzer = self._graph_analyzer()
        try:
            cycles = analyzer.detect_cycles()
        finally:
            analyzer.close()
        return tuple(cycle.nodes for cycle in cycles)

    def detect_god_files(self, rules: ArchitectureRules) -> tuple[GodFile, ...]:
        """Aggregate node centrality to the FILE level and flag god-files.

        Uses :meth:`GraphAnalyzer.compute_centrality` and rolls each node's
        in/out-degree up to its file via the ``nodes.file_path`` column. A file is
        a god-file when its summed fan-in is at/above ``rules.god_file_in_degree``
        (the structural signal) OR its LOC exceeds ``rules.god_file_loc`` (the size
        signal). Disabled entirely when ``rules.no_god_files`` is False. Result is
        sorted by file path for determinism.
        """
        if not rules.no_god_files:
            return ()

        node_files = self._node_file_paths()
        centrality = self._centrality()

        in_by_file: dict[str, int] = {}
        out_by_file: dict[str, int] = {}
        for node_id, cent in centrality.items():
            file_path = node_files.get(node_id)
            if not file_path:
                continue
            in_by_file[file_path] = in_by_file.get(file_path, 0) + cent.in_degree
            out_by_file[file_path] = out_by_file.get(file_path, 0) + cent.out_degree

        loc_by_file = self._loc_by_file()

        candidate_files = set(in_by_file) | set(out_by_file) | set(loc_by_file)
        gods: list[GodFile] = []
        for file_path in sorted(candidate_files):
            in_deg = in_by_file.get(file_path, 0)
            out_deg = out_by_file.get(file_path, 0)
            loc = loc_by_file.get(file_path, 0)
            # One comparator convention for both signals: at-or-above the cap
            # counts. (Previously LOC used strict ``>`` while fan-in used
            # inclusive ``>=`` — a file exactly at the LOC cap was silently
            # passed.)
            over_coupling = in_deg >= rules.god_file_in_degree
            over_size = loc >= rules.god_file_loc
            if over_coupling or over_size:
                gods.append(GodFile(file=file_path, in_degree=in_deg, out_degree=out_deg, loc=loc))
        return tuple(gods)

    def detect_boundaries(
        self,
        layers: tuple[LayerRule, ...],
        boundaries: tuple[BoundaryRule, ...],
    ) -> tuple[BoundaryViolation, ...]:
        """Reject in-memory dependency edges that cross a disallowed boundary.

        Each edge endpoint path is glob-matched to a layer (first matching layer,
        by declared order then name). A directed ``(from_layer -> to_layer)`` pair
        is a violation when an explicit :class:`BoundaryRule` denies it
        (``allow=False``). With no layers/boundaries declared this is a no-op
        (teams opt in). Pure path + edge lookup; deterministic.
        """
        if not layers or not boundaries or not self.scanned_files:
            return ()

        deny: dict[tuple[str, str], BoundaryRule] = {}
        for rule in boundaries:
            if not rule.allow:
                deny[(rule.from_layer, rule.to_layer)] = rule
        if not deny:
            return ()

        # Reuse the cached dependency graph so this pass + ``detect_cycles``
        # share one ``DependencyGraphBuilder().build()`` call per analyzer.
        graph = self._dep_graph_built()
        if graph is None:
            return ()
        ordered_layers = sorted(layers, key=lambda layer: (layer.order, layer.name))

        violations: list[BoundaryViolation] = []
        seen: set[tuple[str, str]] = set()
        for edge in graph.edges:
            if not edge.internal:
                continue
            src_layer = self._layer_of(edge.source, ordered_layers)
            dst_layer = self._layer_of(edge.target, ordered_layers)
            if src_layer is None or dst_layer is None:
                continue
            matched = deny.get((src_layer, dst_layer))
            if matched is None:
                continue
            key = (edge.source, edge.target)
            if key in seen:
                continue
            seen.add(key)
            violations.append(
                BoundaryViolation(
                    source_file=edge.source,
                    target_file=edge.target,
                    from_layer=src_layer,
                    to_layer=dst_layer,
                    reason=matched.reason,
                )
            )
        violations.sort(key=lambda v: (v.source_file, v.target_file))
        return tuple(violations)

    def compute_complexity(
        self,
        rules: ArchitectureRules,
        *,
        files: list[str] | None = None,
    ) -> tuple[ComplexityFinding, ...]:
        """Per-symbol cyclomatic complexity over scope (public; returns only findings).

        Convenience wrapper over :meth:`_compute_complexity` that drops the
        skipped-reasons tuple. Symbols whose complexity exceeds ``rules.max_cc``
        become :class:`ComplexityFinding` rows.
        """
        scope = set(self._normalize_scope(files) or [])
        findings, _ = self._compute_complexity(rules, scope=scope if files is not None else None)
        return findings

    # -- internals --------------------------------------------------------- #

    def _compute_complexity(
        self,
        rules: ArchitectureRules,
        *,
        scope: set[str] | None,
    ) -> tuple[tuple[ComplexityFinding, ...], tuple[str, ...]]:
        """Walk each scanned source file's symbols for cyclomatic complexity.

        Returns ``(findings, skipped)``. When tree-sitter is unavailable every
        file is recorded as ``max_cc:<file>:tree-sitter-unavailable`` and no
        finding is emitted (degrade honestly). Only Python is enumerated in the
        parser's MVP decision set; other languages simply yield no rows.
        """
        if not self.scanned_files:
            return (), ()

        if not self._parser.is_available():
            return (), ("max_cc:tree-sitter-unavailable",)

        findings: list[ComplexityFinding] = []
        for scanned in self.scanned_files:
            rel = Path(scanned.relative_path).as_posix()
            if scope is not None and rel not in scope:
                continue
            rows = self._parser.cyclomatic_complexity(scanned.content, scanned.language)
            for symbol, complexity, line in rows:
                if complexity > rules.max_cc:
                    findings.append(
                        ComplexityFinding(file=rel, symbol=symbol, complexity=complexity, line=line)
                    )
        findings.sort(key=lambda f: (f.file, f.line, f.symbol))
        return tuple(findings), ()

    def _compute_duplication(
        self,
        rules: ArchitectureRules,
        *,
        scope: set[str] | None,
    ) -> tuple[tuple[DuplicationFinding, ...], tuple[str, ...]]:
        """Deterministic in-process near-duplicate (clone) detection.

        For every in-scope function it pulls the normalized body via
        :meth:`TreeSitterParser.function_blocks`, tokenizes it (split on
        non-alphanumeric), windows the tokens into fixed-width ``_DUP_SHINGLE``
        shingles, and forms a shingle set. Two functions are a near-duplicate
        when the shared-shingle count clears ``rules.min_duplicate_tokens`` AND
        their Jaccard overlap is at least ``_DUP_OVERLAP``. ALL function pairs in
        the in-scope set are compared in a fully deterministic order (functions
        sorted by ``(file, line, symbol)``, iterate ``i < j``); functions below
        the minimum size are skipped. One :class:`DuplicationFinding` is emitted
        per flagged pair, the pair ordered canonically.

        Mirrors :meth:`_compute_complexity`: ``((), ())`` when no source is
        scanned, ``((), ('no_duplication:tree-sitter-unavailable',))`` when the
        parser is unavailable. Pure AST + string hashing — no subprocess, no
        model (the ``snapshot`` zero-subprocess contract holds).

        Duplication is a CROSS-file / whole-graph signal like cycles: the shingle
        sets are computed over EVERY in-scope function, and a pair is reported
        when EITHER of its two sites is in ``scope`` (mirrors the cycle
        ``any(member in scope ...)`` rule).
        """
        if not self.scanned_files:
            return (), ()

        if not self._parser.is_available():
            return (), ("no_duplication:tree-sitter-unavailable",)

        # Build the per-function shingle sets over the whole scanned set (a clone
        # may pair an in-scope site with an out-of-scope partner — the cross-file
        # signal needs both sides), then report only pairs touching ``scope``.
        functions: list[_DupFunction] = []
        for scanned in self.scanned_files:
            rel = Path(scanned.relative_path).as_posix()
            for symbol, start_line, _end_line, body in self._parser.function_blocks(
                scanned.content, scanned.language
            ):
                shingles = self._shingles(body)
                # Skip a function below the minimum size (tiny/boilerplate units
                # such as trivial getters never churn the ratchet).
                if len(shingles) < rules.min_duplicate_tokens:
                    continue
                functions.append(
                    _DupFunction(file=rel, symbol=symbol, line=start_line, shingles=shingles)
                )

        # Fully deterministic comparison order.
        functions.sort(key=lambda fn: (fn.file, fn.line, fn.symbol))

        results: list[DuplicationFinding] = []
        for i in range(len(functions)):
            for j in range(i + 1, len(functions)):
                a = functions[i]
                b = functions[j]
                shared = a.shingles & b.shingles
                shared_count = len(shared)
                if shared_count < rules.min_duplicate_tokens:
                    continue
                union = len(a.shingles | b.shingles)
                overlap = shared_count / union if union else 0.0
                if overlap < _DUP_OVERLAP:
                    continue
                # Report only when EITHER site is in scope (cross-file rule).
                if scope is not None and a.file not in scope and b.file not in scope:
                    continue
                # Canonical pair ordering by (file, symbol).
                first, second = a, b
                if (first.file, first.symbol) > (second.file, second.symbol):
                    first, second = b, a
                results.append(
                    DuplicationFinding(
                        file_a=first.file,
                        symbol_a=first.symbol,
                        line_a=first.line,
                        file_b=second.file,
                        symbol_b=second.symbol,
                        line_b=second.line,
                        tokens=shared_count,
                    )
                )
        results.sort(key=lambda d: (d.file_a, d.line_a, d.symbol_a, d.file_b, d.line_b, d.symbol_b))
        return tuple(results), ()

    def _compute_nesting(
        self,
        rules: ArchitectureRules,
        *,
        scope: set[str] | None,
    ) -> tuple[tuple[NestingFinding, ...], tuple[str, ...]]:
        """Per-symbol CODE block-nesting depth over scope (mirrors complexity).

        Calls :meth:`TreeSitterParser.max_nesting_depth`; a row whose depth
        exceeds ``rules.max_nesting`` becomes a :class:`NestingFinding`. Returns
        ``(findings, skipped)``; ``('max_nesting:tree-sitter-unavailable',)`` when
        the parser is unavailable, ``()`` when no source is scanned. Sorted by
        ``(file, line, symbol)``. This is CODE nesting, distinct from the
        directory-depth metric.
        """
        if not self.scanned_files:
            return (), ()

        if not self._parser.is_available():
            return (), ("max_nesting:tree-sitter-unavailable",)

        findings: list[NestingFinding] = []
        for scanned in self.scanned_files:
            rel = Path(scanned.relative_path).as_posix()
            if scope is not None and rel not in scope:
                continue
            rows = self._parser.max_nesting_depth(scanned.content, scanned.language)
            for symbol, depth, line in rows:
                if depth > rules.max_nesting:
                    findings.append(NestingFinding(file=rel, symbol=symbol, depth=depth, line=line))
        findings.sort(key=lambda f: (f.file, f.line, f.symbol))
        return tuple(findings), ()

    @staticmethod
    def _shingles(normalized_body: str) -> frozenset[tuple[str, ...]]:
        """Fixed-width token shingle set for a normalized function body.

        Tokens are the alphanumeric runs of ``normalized_body`` (split on every
        non-alphanumeric char); the tokens are windowed into ``_DUP_SHINGLE``-wide
        shingles. The shingle tuples are hashable and order-independent as a set,
        so the resulting set is deterministic for identical input. A body with
        fewer than ``_DUP_SHINGLE`` tokens yields the empty set (too small to
        clone-match).
        """
        tokens = [tok for tok in re.split(r"[^0-9A-Za-z]+", normalized_body) if tok]
        if len(tokens) < _DUP_SHINGLE:
            return frozenset()
        return frozenset(
            tuple(tokens[i : i + _DUP_SHINGLE]) for i in range(len(tokens) - _DUP_SHINGLE + 1)
        )

    def _build_findings(
        self,
        rules: ArchitectureRules,
        cycles: tuple[tuple[str, ...], ...],
        god_files: tuple[GodFile, ...],
        boundary_violations: tuple[BoundaryViolation, ...],
        complexity: tuple[ComplexityFinding, ...],
        duplication: tuple[DuplicationFinding, ...] = (),
        nesting: tuple[NestingFinding, ...] = (),
    ) -> tuple[Finding, ...]:
        """Normalize every typed result into ``Finding(category='architecture')``."""
        findings: list[Finding] = []

        if len(cycles) > rules.max_cycles:
            for members in cycles:
                preview = " -> ".join(members[:4])
                if len(members) > 4:
                    preview = f"{preview} -> ..."
                # A cycle has no single ``file`` anchor — it spans every member.
                # The full member list lives in ``metadata['members']`` so the
                # trace shows exactly what participates. ``symbol`` carries a
                # STABLE per-cycle fingerprint (``"|".join(members)`` — members
                # are already sorted by Tarjan) so the ratchet key stays unique
                # per distinct SCC. Without this, every cycle across the repo
                # would hash to one key (``max_cycles||`` with file/symbol=None)
                # and a newly-introduced SCC silently masked as "pre-existing".
                cycle_fingerprint = "cycle:" + "|".join(members)
                findings.append(
                    Finding(
                        rule="max_cycles",
                        severity=CheckSeverity.ERROR,
                        message=(f"Import cycle among {len(members)} file(s): {preview}"),
                        file=None,
                        symbol=cycle_fingerprint,
                        suggestion=(
                            "Break the cycle by extracting the shared code or "
                            "inverting a dependency."
                        ),
                        category="architecture",
                        metadata={"members": list(members), "size": len(members)},
                    )
                )

        for god in god_files:
            reasons: list[str] = []
            if god.in_degree >= rules.god_file_in_degree:
                reasons.append(f"fan-in {god.in_degree} >= {rules.god_file_in_degree}")
            if god.loc >= rules.god_file_loc:
                reasons.append(f"{god.loc} LOC >= {rules.god_file_loc}")
            findings.append(
                Finding(
                    rule="no_god_files",
                    severity=CheckSeverity.WARNING,
                    message=f"God file ({'; '.join(reasons)})",
                    file=god.file,
                    symbol=god.file,
                    suggestion="Split this module into smaller, cohesive units.",
                    category="architecture",
                    metadata={
                        "in_degree": god.in_degree,
                        "out_degree": god.out_degree,
                        "loc": god.loc,
                    },
                )
            )

        for violation in boundary_violations:
            detail = f" ({violation.reason})" if violation.reason else ""
            findings.append(
                Finding(
                    rule="layers",
                    severity=CheckSeverity.ERROR,
                    message=(
                        f"Disallowed dependency {violation.from_layer} -> "
                        f"{violation.to_layer}{detail}"
                    ),
                    file=violation.source_file,
                    suggestion="Respect the declared layer boundary or update the rule.",
                    category="architecture",
                    metadata={
                        "target": violation.target_file,
                        "from": violation.from_layer,
                        "to": violation.to_layer,
                    },
                )
            )

        for hotspot in complexity:
            findings.append(
                Finding(
                    rule="max_cc",
                    severity=CheckSeverity.WARNING,
                    message=(
                        f"{hotspot.symbol} has cyclomatic complexity "
                        f"{hotspot.complexity} (> {rules.max_cc})"
                    ),
                    file=hotspot.file,
                    line=hotspot.line,
                    symbol=hotspot.symbol,
                    suggestion="Reduce branching or extract helper functions.",
                    category="architecture",
                    metadata={"complexity": hotspot.complexity},
                )
            )

        # Duplication is gated on its size knob (always on when a pair clears
        # min_duplicate_tokens — the pass already enforced that). The composite
        # ``symbol`` is the canonical pair fingerprint: it is what makes
        # ``finding_key`` UNIQUE per distinct clone-pair (exactly the
        # ``cycle_fingerprint`` precedent). Without it every dup would hash to one
        # key and the ratchet would silently mask new clones.
        if rules.min_duplicate_tokens > 0:
            for dup in duplication:
                pair_fingerprint = f"dup:{dup.file_a}:{dup.symbol_a}|{dup.file_b}:{dup.symbol_b}"
                findings.append(
                    Finding(
                        rule="no_duplication",
                        severity=CheckSeverity.WARNING,
                        message=(
                            f"{dup.symbol_a} duplicates {dup.symbol_b} ({dup.tokens} shared tokens)"
                        ),
                        file=dup.file_a,
                        line=dup.line_a,
                        symbol=pair_fingerprint,
                        suggestion="Extract the shared logic into one reusable unit.",
                        category="architecture",
                        metadata={
                            "file_b": dup.file_b,
                            "symbol_b": dup.symbol_b,
                            "line_b": dup.line_b,
                            "tokens": dup.tokens,
                        },
                    )
                )

        # Nesting gates on its ceiling knob (0 disables), mirroring how
        # ``max_cycles`` gates the cycle block. Symbol-scoped key like ``max_cc``.
        if rules.max_nesting > 0:
            for nest in nesting:
                findings.append(
                    Finding(
                        rule="max_nesting",
                        severity=CheckSeverity.WARNING,
                        message=(
                            f"{nest.symbol} nests {nest.depth} levels deep (> {rules.max_nesting})"
                        ),
                        file=nest.file,
                        line=nest.line,
                        symbol=nest.symbol,
                        suggestion="Flatten with guard clauses or extracted helpers.",
                        category="architecture",
                        metadata={"depth": nest.depth},
                    )
                )

        return tuple(findings)

    def _build_metrics(
        self,
        cycles: tuple[tuple[str, ...], ...],
        god_files: tuple[GodFile, ...],
        complexity: tuple[ComplexityFinding, ...],
        boundary_violations: tuple[BoundaryViolation, ...],
        duplication: tuple[DuplicationFinding, ...],
        nesting: tuple[NestingFinding, ...],
        *,
        scope: set[str] | None,
    ) -> QualityMetrics:
        """Roll the structured results into the integer :class:`QualityMetrics`.

        ``cycles`` here is the WHOLE-graph cycle list (not the scope-filtered one)
        so the headline cycle count is graph-global; the per-file/per-symbol
        metrics use the (already scope-filtered) god-file/complexity/nesting
        results. ``duplication`` counts ALL clone pairs found (a whole-graph
        signal like cycles); ``max_nesting`` uses the scope-filtered nesting rows.
        """
        centrality = self._centrality()
        max_in = max((c.in_degree for c in centrality.values()), default=0)
        max_out = max((c.out_degree for c in centrality.values()), default=0)
        node_count = len(centrality)
        edge_count = sum(c.out_degree for c in centrality.values())

        max_cc = max((h.complexity for h in complexity), default=0)
        max_depth = self._max_depth(scope)
        # Report-only distribution signal: how evenly LOC is spread across files.
        loc_gini_bp = _gini_bp(list(self._loc_by_file().values()))

        return QualityMetrics(
            cycles=len(cycles),
            god_files=len(god_files),
            max_cc=max_cc,
            max_in_degree=max_in,
            max_out_degree=max_out,
            boundary_violations=len(boundary_violations),
            duplication=len(duplication),
            max_depth=max_depth,
            max_nesting=max((n.depth for n in nesting), default=0),
            node_count=node_count,
            edge_count=edge_count,
            loc_gini_bp=loc_gini_bp,
        )

    def _dep_graph_built(self) -> Any:
        """Build the per-instance dependency graph (lazy + cached).

        Returns ``None`` when no source was scanned, mirroring the ``None``
        contract of the previous behavior so ``detect_cycles`` and
        ``detect_boundaries`` short-circuit the same way. The cache lives for
        the lifetime of this :class:`ArchitectureAnalyzer` — the harness gate
        instantiates a fresh one for each dispatch, so the cache never crosses
        a state-changing boundary.
        """
        if self._dep_graph_cache is None and self.scanned_files is not None:
            self._dep_graph_cache = DependencyGraphBuilder().build(self.scanned_files)
        return self._dep_graph_cache

    def _import_adjacency(self) -> dict[str, set[str]]:
        """File-path-keyed import adjacency from the in-memory dependency graph."""
        graph = self._dep_graph_built()
        if graph is None:
            return {}
        adjacency: dict[str, set[str]] = {path: set() for path in graph.nodes}
        for edge in graph.edges:
            if edge.internal and edge.source in adjacency and edge.target in adjacency:
                if edge.source != edge.target:
                    adjacency[edge.source].add(edge.target)
        return adjacency

    def _graph_analyzer(self) -> GraphAnalyzer:
        """Build a :class:`GraphAnalyzer` bound to this project's DB."""
        return GraphAnalyzer(GraphDatabase(self.db_path), edge_kinds=self.edge_kinds)

    def _centrality(self) -> dict[str, Centrality]:
        """Per-node centrality (cached per analyzer lifetime).

        Tolerant of a missing/empty DB — returns ``{}`` so the coupling/god-file
        /metrics passes degrade honestly instead of crashing the whole gate.
        Cached so ``detect_god_files`` and ``_build_metrics`` (both reached
        from ``analyze``) share one sweep rather than two. The cache lives on
        the rename-collided-free ``_centrality_cache`` attribute so it cannot
        shadow this method (Python looks up instance attrs before methods).
        """
        if self._centrality_cache is not None:
            return self._centrality_cache
        if not self.db_path.exists():
            self._centrality_cache = {}
            return self._centrality_cache
        analyzer = self._graph_analyzer()
        try:
            self._centrality_cache = dict(analyzer.compute_centrality())
        finally:
            analyzer.close()
        return self._centrality_cache

    def _node_file_paths(self) -> dict[str, str]:
        """Map ``node_id -> file_path`` straight from the ``nodes`` table (cached).

        Tolerant of a missing/empty DB (returns ``{}``) so the god-file pass
        degrades to LOC-only rather than raising. Cached because both the
        god-file roll-up and any related centrality-based lookup on the same
        analyzer instance need exactly this map.
        """
        if self._node_files_cache is not None:
            return self._node_files_cache
        if not self.db_path.exists():
            self._node_files_cache = {}
            return self._node_files_cache
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute("SELECT id, file_path FROM nodes").fetchall()
            finally:
                conn.close()
        except sqlite3.Error:
            self._node_files_cache = {}
            return self._node_files_cache
        self._node_files_cache = {
            str(row["id"]): Path(row["file_path"]).as_posix() for row in rows if row["file_path"]
        }
        return self._node_files_cache

    def _loc_by_file(self) -> dict[str, int]:
        """Per-file line count from the scanned source (POSIX-relative keys)."""
        loc: dict[str, int] = {}
        for scanned in self.scanned_files or []:
            rel = Path(scanned.relative_path).as_posix()
            loc[rel] = scanned.content.count("\n") + (1 if scanned.content else 0)
        return loc

    def _max_depth(self, scope: set[str] | None) -> int:
        """Deepest directory nesting among the in-scope (or all scanned) files."""
        files: list[str]
        if scope is not None:
            files = sorted(scope)
        else:
            files = [Path(s.relative_path).as_posix() for s in (self.scanned_files or [])]
        depth = 0
        for path in files:
            # Number of directory separators == nesting depth of the file.
            depth = max(depth, Path(path).as_posix().count("/"))
        return depth

    @staticmethod
    def _normalize_scope(changed_files: list[str] | None) -> set[str] | None:
        """POSIX-normalize the changed-file scope, or ``None`` for whole-graph."""
        if changed_files is None:
            return None
        return {Path(p).as_posix() for p in changed_files}

    @staticmethod
    def _layer_of(path: str, ordered_layers: tuple[LayerRule, ...] | list[LayerRule]) -> str | None:
        """First layer whose glob patterns match ``path`` (already ordered)."""
        normalized = Path(path).as_posix()
        for layer in ordered_layers:
            for pattern in layer.paths:
                if fnmatch.fnmatch(normalized, pattern):
                    return layer.name
        return None
