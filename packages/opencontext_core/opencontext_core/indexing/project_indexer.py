"""Project indexer that builds a persistent project manifest."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from opencontext_core.compat import UTC
from opencontext_core.config import ProjectIndexConfig
from opencontext_core.indexing.dependency_graph import DependencyGraphBuilder
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
from opencontext_core.indexing.scanner import ProjectScanner, ScannedFile
from opencontext_core.indexing.symbol_extractor import ExtractableFile, SymbolExtractor
from opencontext_core.indexing.tree_sitter_parser import LANGUAGE_EXTENSIONS
from opencontext_core.models.project import ProjectManifest, Symbol
from opencontext_core.paths import StorageMode, resolve_storage_path
from opencontext_core.project.profiles import (
    GENERIC_PROFILE,
    GenericTechnologyProfile,
    ProfileDetectionResult,
    TechnologyProfile,
    scanners_for_profiles,
)

_log = logging.getLogger(__name__)

# Languages the tree-sitter parser has real symbol extractors for. Files in other
# languages are still scanned/searchable but don't get graph symbols+edges. Keep
# in sync with TreeSitterParser._parse_with_tree_sitter.
_KG_LANGUAGES = frozenset({"python", "javascript", "typescript", "go", "rust", "java", "php"})

# File extensions whose language the KG extracts symbols for. Used to decide which
# changed files to re-index after a task (kept in sync with _KG_LANGUAGES).
_KG_EXTENSIONS = frozenset(
    ext for ext, lang in LANGUAGE_EXTENSIONS.items() if lang in _KG_LANGUAGES
)


class ProjectIndexer:
    """Builds project intelligence manifests from filesystem state."""

    def __init__(
        self,
        config: ProjectIndexConfig,
        project_name: str,
        profiles: list[TechnologyProfile] | None = None,
        knowledge_graph: KnowledgeGraph | None = None,
    ) -> None:
        self.config = config
        self.project_name = project_name
        self.scanner = ProjectScanner(config.ignore)
        self.symbol_extractor = SymbolExtractor()
        self.profiles = profiles or [GenericTechnologyProfile()]
        self.knowledge_graph = knowledge_graph

    def build_manifest(self, root: Path | None = None) -> ProjectManifest:
        """Scan and analyze a project root."""

        project_root = (root or Path(self.config.root)).resolve()
        scanned_files = self.scanner.scan(project_root)
        project_files = [scanned_file.to_project_file() for scanned_file in scanned_files]
        symbols = self._extract_symbols(scanned_files)
        dependency_graph = DependencyGraphBuilder().build(scanned_files)
        detections = self._detect_profiles(project_root, [file.path for file in project_files])
        profiles = self._profiles_from_detections(detections)
        primary_profile = self._primary_profile(detections, profiles, scanned_files)

        # Populate knowledge graph with batch checkpointing
        # Checkpoint persists which files have been indexed so interrupted runs resume.
        kg_stats: dict[str, Any] = {"files_indexed": 0, "nodes": 0, "edges": 0}
        if self.knowledge_graph is not None:
            checkpoint_path = (
                resolve_storage_path(project_root, StorageMode.local) / "index_checkpoint.json"
            )
            # K3: checkpoint is now dict[str, float] (path → mtime); legacy list
            # format is transparently upgraded to empty dict → one-time full reindex.
            done_mtimes: dict[str, float] = _load_checkpoint(checkpoint_path)
            # K4 (checkpoint validity guard): the checkpoint is only meaningful
            # relative to an existing, non-empty KG database.  When the KG has
            # zero nodes — because install indexed into a different storage path,
            # the DB was cleared, or this is the very first real index run — the
            # checkpoint is stale evidence and must be ignored so files are
            # re-indexed into the live database.
            if done_mtimes:
                try:
                    _kg_nodes = self.knowledge_graph.db.get_stats().get("nodes", 0)
                    if _kg_nodes == 0:
                        _log.debug(
                            "indexer: checkpoint exists but KG has 0 nodes "
                            "— ignoring checkpoint, full reindex"
                        )
                        done_mtimes = {}
                except Exception as _exc:
                    _log.debug("indexer: checkpoint validity check failed (%s), proceeding", _exc)
            indexed_files: list[tuple[str, str]] = []
            batch_size = 50
            batch_count = 0
            # K2: per-language count of files in _KG_LANGUAGES that were counted
            # but not actually AST-parsed (grammar unavailable + regex yields nothing).
            unparsed_by_lang: dict[str, int] = {}
            for scanned_file in scanned_files:
                if scanned_file.language not in _KG_LANGUAGES:
                    continue
                # K3: skip if mtime is unchanged since last checkpoint
                try:
                    current_mtime = scanned_file.path.stat().st_mtime
                except OSError:
                    current_mtime = 0.0
                stored_mtime = done_mtimes.get(scanned_file.relative_path)
                if stored_mtime is not None and stored_mtime == current_mtime:
                    kg_stats["files_indexed"] += 1
                    kg_stats["skipped_unchanged"] = kg_stats.get("skipped_unchanged", 0) + 1
                    indexed_files.append((scanned_file.relative_path, scanned_file.content))
                    continue
                try:
                    stats = self.knowledge_graph.index_file(
                        scanned_file.relative_path, scanned_file.content
                    )
                    kg_stats["files_indexed"] += 1
                    kg_stats["nodes"] += stats.get("nodes", 0)
                    kg_stats["edges"] += stats.get("edges", 0)
                    # K2: detect "counted but not parsed" — regex fallback with zero nodes
                    if stats.get("parse_mode") == "regex" and stats.get("nodes", 0) == 0:
                        lang = scanned_file.language
                        unparsed_by_lang[lang] = unparsed_by_lang.get(lang, 0) + 1
                    indexed_files.append((scanned_file.relative_path, scanned_file.content))
                    # K3: record current mtime in checkpoint
                    done_mtimes[scanned_file.relative_path] = current_mtime
                    # K3: track how many files were actually re-indexed (mtime changed or new)
                    kg_stats["reindexed_changed"] = kg_stats.get("reindexed_changed", 0) + 1
                    batch_count += 1
                    if batch_count % batch_size == 0:
                        _save_checkpoint(checkpoint_path, done_mtimes)
                except Exception as exc:
                    # A broken parser must not silently shrink the graph — count and
                    # log it so a systematically-failing file is visible, not hidden.
                    kg_stats["files_failed"] = kg_stats.get("files_failed", 0) + 1
                    _log.warning("indexing failed for %s: %s", scanned_file.relative_path, exc)
            _save_checkpoint(checkpoint_path, done_mtimes)
            if kg_stats.get("files_failed"):
                _log.warning(
                    "indexing: %d file(s) failed to index — graph may be incomplete",
                    kg_stats["files_failed"],
                )
            # K2: surface unparsed-file counts and emit one honest log line per language
            if unparsed_by_lang:
                kg_stats["unparsed_files"] = unparsed_by_lang
                for lang, count in sorted(unparsed_by_lang.items()):
                    _log.warning(
                        "%d %s file(s) counted but not parsed — grammar unavailable",
                        count,
                        lang,
                    )
            # Single FTS5 rebuild after all files are indexed (was per-file — huge speedup)
            try:
                self.knowledge_graph.db.rebuild_fts()
            except Exception as exc:
                _log.warning("FTS rebuild failed: %s", exc)
            if indexed_files:
                try:
                    cross = self.knowledge_graph.finalize_cross_file_edges(indexed_files)
                    kg_stats["edges"] += cross
                except Exception as exc:
                    _log.warning("cross-file edge finalization failed: %s", exc)
            # Reconcile the graph to the freshly-scanned set: drop files (and their
            # nodes/edges) that were indexed on a prior run but are no longer scanned
            # — a since-deleted file, or a vendored tree now excluded by ignore rules
            # (e.g. a venv). Without this, index_file only ever unioned new files in,
            # so orphaned nodes accumulated and surfaced as retrieval evidence. Guarded
            # to a COMPLETE pass: a run that failed every file (files_failed but nothing
            # indexed) must not wipe the existing graph. ``indexed_files`` is the
            # authoritative current set (newly-indexed + checkpoint-resumed), so a
            # resumed/partial run still keeps the files it already has.
            if indexed_files:
                try:
                    pruned = self.knowledge_graph.db.prune_files_absent_from(
                        path for path, _content in indexed_files
                    )
                    if pruned:
                        kg_stats["files_pruned"] = pruned
                        _log.info("knowledge graph: pruned %d stale file(s)", pruned)
                except Exception as exc:
                    _log.warning("knowledge graph reconciliation failed: %s", exc)
            # Authoritative totals: the incremental counters miss the nodes/edges of
            # files skipped on a resumed run (already in the checkpoint), so read the
            # real counts from the graph instead of under-reporting them.
            try:
                real = self.knowledge_graph.db.get_stats()
                kg_stats["nodes"] = real.get("nodes", kg_stats["nodes"])
                kg_stats["edges"] = real.get("edges", kg_stats["edges"])
            except Exception as exc:
                _log.debug("kg get_stats failed: %s", exc)
            # K3: persist the final mtime registry so the next run can skip
            # unchanged files.  The checkpoint is now a permanent per-project
            # registry (dict[path, mtime]), not a one-shot resumption marker.
            _save_checkpoint(checkpoint_path, done_mtimes)

        # Run route scanners for detected profiles
        detected_profile_names = [
            d.profile for d in detections if d.profile != GENERIC_PROFILE and d.score > 0
        ]
        routes = []
        for scanner in scanners_for_profiles(detected_profile_names):
            routes.extend(scanner.scan(project_root, [file.path for file in project_files]))

        metadata = {
            "file_count": len(project_files),
            "symbol_count": len(symbols),
            "routes": [route.model_dump() for route in routes],
            "safety": {
                "files_with_potential_secrets": [
                    file.path
                    for file in project_files
                    if file.metadata.get("contains_potential_secrets")
                ],
                "warnings": sorted(
                    {
                        str(file.metadata["safety_warning"])
                        for file in project_files
                        if "safety_warning" in file.metadata
                    }
                ),
            },
            "technology_profile_detections": [
                {
                    "profile": detection.profile,
                    "score": detection.score,
                    "markers": detection.markers,
                }
                for detection in detections
            ],
            "dependency_graph": {
                "nodes": len(dependency_graph.nodes),
                "internal_edges": len(dependency_graph.edges),
                "unresolved_edges": len(dependency_graph.unresolved),
            },
            "ignore_patterns": self.config.ignore,
            "knowledge_graph": kg_stats,
        }
        return ProjectManifest(
            project_name=self.project_name,
            root=str(project_root),
            profile=primary_profile,
            technology_profiles=profiles,
            files=project_files,
            symbols=symbols,
            dependency_graph=dependency_graph,
            generated_at=datetime.now(tz=UTC),
            metadata=metadata,
        )

    def _extract_symbols(self, scanned_files: list[ScannedFile]) -> list[Symbol]:
        symbols: list[Symbol] = []
        for scanned_file in scanned_files:
            extractable = ExtractableFile(
                relative_path=scanned_file.relative_path,
                language=scanned_file.language,
                content=scanned_file.content,
            )
            symbols.extend(self.symbol_extractor.extract(extractable))
        return sorted(symbols, key=lambda symbol: (symbol.path, symbol.line, symbol.name))

    def _detect_profiles(
        self,
        project_root: Path,
        paths: list[str],
    ) -> list[ProfileDetectionResult]:
        detectors = [*self.profiles]
        if not any(profile.name == GENERIC_PROFILE for profile in detectors):
            detectors.append(GenericTechnologyProfile())
        return [profile.detect(project_root, paths) for profile in detectors]

    def _profiles_from_detections(
        self,
        detections: list[ProfileDetectionResult],
    ) -> list[str]:
        detected: list[str] = [
            detection.profile
            for detection in detections
            if detection.profile != GENERIC_PROFILE and detection.score > 0
        ]
        if self.config.profile != GENERIC_PROFILE and self.config.profile not in detected:
            detected.append(self.config.profile)
        if not detected:
            detected.append(GENERIC_PROFILE)
        return detected

    def _primary_profile(
        self,
        detections: list[ProfileDetectionResult],
        profiles: list[str],
        scanned_files: list[ScannedFile] | None = None,
    ) -> str:
        if self.config.profile != GENERIC_PROFILE:
            return self.config.profile
        non_generic = [
            detection
            for detection in detections
            if detection.profile != GENERIC_PROFILE and detection.score > 0
        ]
        lang_counts = Counter(
            f.language for f in (scanned_files or []) if getattr(f, "language", None)
        )
        known = {detection.profile for detection in detections}
        if non_generic:
            top = max(non_generic, key=lambda detection: detection.score)
            # When the top detection is a *language* profile (its name is a language
            # with source files here), prefer the dominant code language if another
            # has strictly more files — marker-based detection misses a language with
            # loose source files (e.g. .py with no pyproject.toml), so a 2-python +
            # 1-js repo should be "python", not "javascript". Framework profiles keep
            # priority since their name is a marker/runtime, not a per-file language.
            if top.profile in lang_counts:
                top_files = lang_counts.get(top.profile, 0)
                for language, count in lang_counts.most_common():
                    if language in known and count > top_files:
                        return language
            return top.profile
        # Nothing detected by markers — fall back to the dominant code language that
        # has a known profile (ignores yaml/markdown/… which have no profile).
        for language, _count in lang_counts.most_common():
            if language in known:
                return language
        return profiles[0]


def _load_checkpoint(path: Path) -> dict[str, float]:
    """Load the index checkpoint, returning a ``{path: mtime}`` dict.

    Handles two formats:
    - New format: JSON object ``{path: mtime_float, ...}``
    - Legacy format: JSON array of paths — returns ``{}`` so the next run
      performs a full reindex, then persists the mtime-dict format.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): float(v) for k, v in data.items()}
        # Legacy list format — force full reindex, do not raise
        return {}
    except Exception:
        return {}


def _save_checkpoint(path: Path, done: dict[str, float]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(done), encoding="utf-8")
    except Exception:
        pass
