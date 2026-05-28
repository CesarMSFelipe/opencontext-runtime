"""Extension registry — search, install, list, and remove workflow extensions."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from opencontext_core.workflow.extensions import ExtensionManifest

EXTENSIONS_DIR = ".opencontext/extensions"

BUILTIN_INDEX: list[dict[str, Any]] = [
    {
        "name": "strict-review",
        "version": "1.0.0",
        "description": "Adds a strict multi-reviewer step to SDD review phase.",
        "author": "opencontext-team",
        "tags": ["review", "sdd", "quality"],
        "requires_version": "0.4.0",
    },
    {
        "name": "gh-issues-tracker",
        "version": "1.0.0",
        "description": "Syncs SDD tasks to GitHub Issues automatically after apply.",
        "author": "opencontext-team",
        "tags": ["github", "issues", "automation"],
        "requires_version": "0.4.0",
    },
    {
        "name": "cost-guard",
        "version": "1.0.0",
        "description": "Blocks SDD phases that exceed per-phase token budget.",
        "author": "opencontext-team",
        "tags": ["cost", "budget", "safety"],
        "requires_version": "0.4.0",
    },
    {
        "name": "framework-router",
        "version": "1.0.0",
        "description": "Framework-aware route detection for Django, FastAPI, Flask, Express, NestJS.",
        "author": "opencontext-team",
        "tags": ["routing", "framework", "django", "fastapi", "express"],
        "requires_version": "0.4.0",
    },
    {
        "name": "party-review",
        "version": "1.0.0",
        "description": "Multi-perspective LLM review with architect, security, performance, and UX roles.",
        "author": "opencontext-team",
        "tags": ["review", "llm", "quality", "security"],
        "requires_version": "0.4.0",
    },
    {
        "name": "token-telemetry",
        "version": "1.0.0",
        "description": "Tracks cumulative token savings and context efficiency over time.",
        "author": "opencontext-team",
        "tags": ["telemetry", "cost", "tokens", "analytics"],
        "requires_version": "0.4.0",
    },
    {
        "name": "bridge-detector",
        "version": "1.0.0",
        "description": "Cross-language call boundary detection for HTTP, gRPC, subprocess, and IPC.",
        "author": "opencontext-team",
        "tags": ["polyglot", "bridges", "cross-language", "detection"],
        "requires_version": "0.4.0",
    },
]


class ExtensionRegistry:
    """Client for the OpenContext extension registry."""

    def __init__(self, index: list[dict[str, Any]] | None = None) -> None:
        self._index = index if index is not None else BUILTIN_INDEX

    def search(self, query: str = "") -> list[dict[str, Any]]:
        """Search extensions by name, description, or tag.

        Returns all entries if query is empty.
        """
        q = query.lower().strip()
        if not q:
            return list(self._index)
        return [
            ext
            for ext in self._index
            if q in ext.get("name", "").lower()
            or q in ext.get("description", "").lower()
            or any(q in tag.lower() for tag in ext.get("tags", []))
        ]

    def install(self, name: str, root: str | Path = ".") -> Path:
        """Install an extension from the registry into the project.

        Creates `.opencontext/extensions/<name>/manifest.yaml` with the
        extension metadata. Returns the installation path.
        Raises ValueError if the extension is not found in the registry.
        """
        matches = [e for e in self._index if e.get("name") == name]
        if not matches:
            msg = f"Extension not found in registry: {name!r}"
            raise ValueError(msg)

        ext_data = matches[0]
        ext_dir = Path(root) / EXTENSIONS_DIR / name
        ext_dir.mkdir(parents=True, exist_ok=True)

        import yaml

        manifest_path = ext_dir / "manifest.yaml"
        manifest_path.write_text(yaml.safe_dump(ext_data, sort_keys=False), encoding="utf-8")
        return ext_dir

    def list_installed(self, root: str | Path = ".") -> list[ExtensionManifest]:
        """Return validated manifests for all installed extensions."""
        base = Path(root) / EXTENSIONS_DIR
        if not base.exists():
            return []
        manifests: list[ExtensionManifest] = []
        for manifest_path in sorted(base.glob("*/manifest.yaml")):
            try:
                manifests.append(ExtensionManifest.from_yaml(manifest_path))
            except Exception:
                pass
        return manifests

    def remove(self, name: str, root: str | Path = ".") -> bool:
        """Remove an installed extension.

        Returns True if the extension was removed, False if it was not found.
        """
        ext_dir = Path(root) / EXTENSIONS_DIR / name
        if not ext_dir.exists():
            return False
        shutil.rmtree(ext_dir)
        return True
