"""Project indexer that builds a persistent project manifest."""

from __future__ import annotations

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

        # Populate knowledge graph if available
        kg_stats = {"files_indexed": 0, "nodes": 0, "edges": 0}
        if self.knowledge_graph is not None:
            for scanned_file in scanned_files:
                if scanned_file.language in ("python", "php"):
                    try:
                        stats = self.knowledge_graph.index_file(
                            scanned_file.relative_path, scanned_file.content
                        )
                        kg_stats["files_indexed"] += 1
                        kg_stats["nodes"] += stats.get("nodes", 0)
                        kg_stats["edges"] += stats.get("edges", 0)
                    except Exception:
                        pass

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
