"""Project indexer that builds a persistent project manifest."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from opencontext_core.compat import UTC
from opencontext_core.config import ProjectIndexConfig
from opencontext_core.indexing.dependency_graph import DependencyGraphBuilder
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
from opencontext_core.indexing.scanner import ProjectScanner, ScannedFile
from opencontext_core.indexing.symbol_extractor import ExtractableFile, SymbolExtractor
from opencontext_core.models.project import ProjectManifest, Symbol
from opencontext_core.project.profiles import (
    GENERIC_PROFILE,
    GenericTechnologyProfile,
    ProfileDetectionResult,
    TechnologyProfile,
    scanners_for_profiles,
)

_log = logging.getLogger(__name__)


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
        primary_profile = self._primary_profile(detections, profiles)

        # Populate knowledge graph with batch checkpointing
        # Checkpoint persists which files have been indexed so interrupted runs resume.
        kg_stats = {"files_indexed": 0, "nodes": 0, "edges": 0}
        if self.knowledge_graph is not None:
            checkpoint_path = project_root / ".storage" / "opencontext" / "index_checkpoint.json"
            done_paths: set[str] = _load_checkpoint(checkpoint_path)
            indexed_files: list[tuple[str, str]] = []
            batch_size = 50
            batch_count = 0
            for scanned_file in scanned_files:
                if scanned_file.language not in ("python", "php"):
                    continue
                if scanned_file.relative_path in done_paths:
                    kg_stats["files_indexed"] += 1
                    indexed_files.append((scanned_file.relative_path, scanned_file.content))
                    continue
                try:
                    stats = self.knowledge_graph.index_file(
                        scanned_file.relative_path, scanned_file.content
                    )
                    kg_stats["files_indexed"] += 1
                    kg_stats["nodes"] += stats.get("nodes", 0)
                    kg_stats["edges"] += stats.get("edges", 0)
                    indexed_files.append((scanned_file.relative_path, scanned_file.content))
                    done_paths.add(scanned_file.relative_path)
                    batch_count += 1
                    if batch_count % batch_size == 0:
                        _save_checkpoint(checkpoint_path, done_paths)
                except Exception as exc:
                    # A broken parser must not silently shrink the graph — count and
                    # log it so a systematically-failing file is visible, not hidden.
                    kg_stats["files_failed"] = kg_stats.get("files_failed", 0) + 1
                    _log.warning("indexing failed for %s: %s", scanned_file.relative_path, exc)
            _save_checkpoint(checkpoint_path, done_paths)
            if kg_stats.get("files_failed"):
                _log.warning(
                    "indexing: %d file(s) failed to index — graph may be incomplete",
                    kg_stats["files_failed"],
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
            # Clear checkpoint after successful full index
            try:
                checkpoint_path.unlink(missing_ok=True)
            except Exception as exc:
                _log.debug("checkpoint cleanup failed: %s", exc)

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
    ) -> str:
        if self.config.profile != GENERIC_PROFILE:
            return self.config.profile
        non_generic = [
            detection
            for detection in detections
            if detection.profile != GENERIC_PROFILE and detection.score > 0
        ]
        if non_generic:
            return max(non_generic, key=lambda detection: detection.score).profile
        return profiles[0]


def _load_checkpoint(path: Path) -> set[str]:
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_checkpoint(path: Path, done: set[str]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(done)), encoding="utf-8")
    except Exception:
        pass
