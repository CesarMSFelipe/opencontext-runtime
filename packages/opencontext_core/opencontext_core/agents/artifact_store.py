"""Artifact store abstraction for SDD artifacts.

Provides pluggable backends: engram, openspec, hybrid, none.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ArtifactStore(ABC):
    """Abstract base for artifact storage backends."""

    @abstractmethod
    def save(self, change: str, artifact: str, content: str) -> str:
        """Save an artifact and return its reference."""

    @abstractmethod
    def load(self, change: str, artifact: str) -> str | None:
        """Load an artifact by change and artifact type."""

    @abstractmethod
    def list_artifacts(self, change: str) -> list[str]:
        """List all artifact types for a change."""


class EngramStore(ArtifactStore):
    """Engram memory backend for artifact storage."""

    def save(self, change: str, artifact: str, content: str) -> str:
        # Engram save is handled by the calling agent; this is a placeholder
        # In practice, the orchestrator calls mem_save directly
        return f"engram:sdd/{change}/{artifact}"

    def load(self, change: str, artifact: str) -> str | None:
        # Engram load is handled by mem_search + mem_get_observation
        return None

    def list_artifacts(self, change: str) -> list[str]:
        return []


class OpenSpecStore(ArtifactStore):
    """OpenSpec file-based backend for artifact storage."""

    def __init__(self, root: str | Path = "openspec/") -> None:
        self.root = Path(root)

    def save(self, change: str, artifact: str, content: str) -> str:
        path = self._path(change, artifact)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path)

    def load(self, change: str, artifact: str) -> str | None:
        path = self._path(change, artifact)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def list_artifacts(self, change: str) -> list[str]:
        change_dir = self.root / "changes" / change
        if not change_dir.exists():
            return []

        artifacts: list[str] = []
        for path in change_dir.iterdir():
            if path.is_file() and path.suffix == ".md":
                artifacts.append(path.stem)

        return sorted(artifacts)

    def _path(self, change: str, artifact: str) -> Path:
        return self.root / "changes" / change / f"{artifact}.md"


class HybridStore(ArtifactStore):
    """Combined Engram + OpenSpec backend."""

    def __init__(self, openspec_root: str | Path = "openspec/") -> None:
        self.engram = EngramStore()
        self.openspec = OpenSpecStore(root=openspec_root)

    def save(self, change: str, artifact: str, content: str) -> str:
        self.openspec.save(change, artifact, content)
        return self.engram.save(change, artifact, content)

    def load(self, change: str, artifact: str) -> str | None:
        # Prefer OpenSpec for load (more reliable)
        return self.openspec.load(change, artifact)

    def list_artifacts(self, change: str) -> list[str]:
        return self.openspec.list_artifacts(change)


class NoneStore(ArtifactStore):
    """No-op backend for inline-only mode."""

    def save(self, change: str, artifact: str, content: str) -> str:
        return "none"

    def load(self, change: str, artifact: str) -> str | None:
        return None

    def list_artifacts(self, change: str) -> list[str]:
        return []
