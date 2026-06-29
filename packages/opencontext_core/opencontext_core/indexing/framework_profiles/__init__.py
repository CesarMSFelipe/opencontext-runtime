"""Framework-convention extraction profiles (PR-008, KG-13).

Detects the project's PHP framework (Drupal/Symfony) and extracts its routes,
services, config, and tests as typed KG v2 nodes/edges (OC-KG-001 §14-15). Also
provides a first-pass generic YAML/JSON/Markdown fact extractor so config/doc files
become ``config`` graph nodes regardless of framework.

Python/TypeScript symbol extraction stays in the tree-sitter pipeline; this module
is the typed seam for the convention-driven (PHP/config/doc) facts.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.indexing.framework_profiles.base import (
    FrameworkExtraction,
    FrameworkProfile,
    evidence_for,
    rel,
)
from opencontext_core.indexing.framework_profiles.drupal import DrupalProfile
from opencontext_core.indexing.framework_profiles.symfony import SymfonyProfile
from opencontext_core.models.kg_v2 import KgNode, KgNodeType, kg_node_id

__all__ = [
    "DrupalProfile",
    "FrameworkExtraction",
    "FrameworkProfile",
    "SymfonyProfile",
    "detect_profile",
    "extract_doc_config_facts",
    "extract_framework_facts",
]

_PROFILES: tuple[FrameworkProfile, ...] = (DrupalProfile(), SymfonyProfile())

_SKIP_DIRS = frozenset({".git", "vendor", "node_modules", "__pycache__", ".venv", "venv"})
_CONFIG_EXTS = frozenset({".yaml", ".yml", ".json"})
_DOC_EXTS = frozenset({".md", ".markdown"})


def detect_profile(root: Path) -> FrameworkProfile | None:
    """Return the first matching framework profile for ``root``, or None."""
    for profile in _PROFILES:
        try:
            if profile.detect(root):
                return profile
        except Exception:
            continue
    return None


def extract_framework_facts(root: Path) -> FrameworkExtraction:
    """Detect the framework and extract its facts; empty when none detected."""
    profile = detect_profile(root)
    if profile is None:
        return FrameworkExtraction()
    try:
        return profile.extract(root)
    except Exception:
        return FrameworkExtraction()


def extract_doc_config_facts(root: Path) -> FrameworkExtraction:
    """First-pass generic extraction of YAML/JSON config + Markdown doc facts.

    Emits one ``config`` node per YAML/JSON file and one ``config`` node (kind FILE)
    per Markdown file (named by its first H1 heading when present). This is a
    deliberately modest seam — deep per-key extraction is left to framework profiles.
    """
    out = FrameworkExtraction()
    for path in root.rglob("*"):
        if not path.is_file() or any(part in _SKIP_DIRS for part in path.parts):
            continue
        suffix = path.suffix.lower()
        rel_path = rel(root, path)
        if suffix in _CONFIG_EXTS:
            out.nodes.append(
                KgNode(
                    id=kg_node_id("config", rel_path),
                    type=KgNodeType.CONFIG,
                    name=path.name,
                    path=rel_path,
                    evidence=[evidence_for(rel_path, confidence=0.6)],
                )
            )
        elif suffix in _DOC_EXTS:
            title = _markdown_title(path) or path.name
            out.nodes.append(
                KgNode(
                    id=kg_node_id("file", rel_path),
                    type=KgNodeType.FILE,
                    name=title,
                    path=rel_path,
                    properties={"doc": True},
                    evidence=[evidence_for(rel_path, confidence=0.6)],
                )
            )
    return out


def _markdown_title(path: Path) -> str:
    """First level-1 heading of a Markdown file, or "" when absent."""
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
    except OSError:
        return ""
    return ""
