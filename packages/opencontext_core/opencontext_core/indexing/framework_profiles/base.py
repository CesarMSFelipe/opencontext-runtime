"""Shared types + helpers for framework-convention extraction (PR-008, KG-13).

A framework profile turns framework config (YAML) into typed KG v2 nodes/edges with
evidence, so PHP/Drupal/Symfony tasks retrieve routes/services/config as graph facts
(OC-KG-001 §14-15). Profiles are convention-detected and skip gracefully when their
markers are absent.

Layering (doc 58): L4 (KG substrate). Imports L0 models + stdlib + PyYAML only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from opencontext_core.models.evidence import EvidenceRef
from opencontext_core.models.kg_v2 import KgEdge, KgNode


@dataclass
class FrameworkExtraction:
    """Typed nodes + edges extracted from a framework project."""

    nodes: list[KgNode] = field(default_factory=list)
    edges: list[KgEdge] = field(default_factory=list)

    def merge(self, other: FrameworkExtraction) -> None:
        """Fold another extraction's nodes/edges into this one."""
        self.nodes.extend(other.nodes)
        self.edges.extend(other.edges)


class FrameworkProfile(Protocol):
    """A convention-detected framework extractor."""

    name: str

    def detect(self, root: Path) -> bool:
        """True when the project matches this framework's markers."""
        ...

    def extract(self, root: Path) -> FrameworkExtraction:
        """Extract typed facts from the project. Empty when nothing matches."""
        ...


def load_yaml(path: Path) -> dict[str, Any]:
    """Safe-load a YAML mapping, returning {} on any error or non-mapping content."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def evidence_for(rel_path: str, *, confidence: float = 0.9) -> EvidenceRef:
    """Build a file-sourced :class:`EvidenceRef` for a framework fact."""
    return EvidenceRef(
        source=rel_path,
        source_type="file",
        confidence=confidence,
        path=rel_path,
    )


def rel(root: Path, path: Path) -> str:
    """Project-relative POSIX path for ``path`` under ``root`` (falls back to name)."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name
