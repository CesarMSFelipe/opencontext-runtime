"""Retrieval source contracts and disabled-by-default adapter policy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC
from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.models.context import ContextItem
from opencontext_core.models.project import DependencyGraph, FileKind, ProjectFile, ProjectManifest
from opencontext_core.retrieval.retriever import ProjectRetriever


class AdapterPolicy(BaseModel):
    """Policy gate for optional retrieval adapters."""

    model_config = ConfigDict(extra="forbid")

    enabled_adapters: list[str] = Field(
        default_factory=list,
        description="Adapter names explicitly enabled by policy.",
    )

    def allows(self, adapter_name: str) -> bool:
        """Return whether an optional adapter may execute."""

        return adapter_name in self.enabled_adapters


class AdapterProtocol(Protocol):
    """Optional evidence adapter; callers must check policy before execution."""

    name: str

    policy_id: str

    def retrieve(self, query: str, limit: int) -> list[ContextItem]:
        """Return evidence candidates when explicitly enabled."""


class ManifestFallbackSource:
    """Native manifest fallback source that is always available."""

    name = "manifest"

    policy_id = "native-manifest"

    def __init__(self, manifest: ProjectManifest) -> None:
        self._retriever = ProjectRetriever(manifest)

    @classmethod
    def from_files(cls, *, root: Path, files: Mapping[str, str]) -> ManifestFallbackSource:
        """Create a small manifest fallback source for tests and local planning."""

        manifest_files: list[ProjectFile] = []
        for relative_path, content in files.items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            manifest_files.append(
                ProjectFile(
                    id=relative_path,
                    path=relative_path,
                    language="python",
                    file_type=FileKind.CODE,
                    tokens=estimate_tokens(content),
                    size_bytes=path.stat().st_size,
                    summary=content.splitlines()[0] if content.splitlines() else relative_path,
                )
            )
        manifest = ProjectManifest(
            project_name="manifest-fallback",
            root=str(root),
            profile="python",
            technology_profiles=["python"],
            files=manifest_files,
            symbols=[],
            dependency_graph=DependencyGraph(
                nodes=[file.path for file in manifest_files],
                edges=[],
                unresolved=[],
                generated_at=datetime.now(tz=UTC),
            ),
            generated_at=datetime.now(tz=UTC),
        )
        return cls(manifest)

    def retrieve(self, query: str, limit: int) -> list[ContextItem]:
        """Return manifest candidates with native source metadata."""

        return [_with_manifest_source(item) for item in self._retriever.retrieve(query, limit)]

    def retrieve_with_policy(
        self,
        query: str,
        limit: int,
        policy: AdapterPolicy,
        adapters: Sequence[AdapterProtocol] = (),
    ) -> list[ContextItem]:
        """Retrieve manifest fallback plus only explicitly enabled optional adapters."""

        items = self.retrieve(query, limit)
        remaining = max(0, limit - len(items))
        for adapter in adapters:
            if remaining <= 0:
                break
            if policy.allows(adapter.name):
                items.extend(adapter.retrieve(query, remaining))
                remaining = max(0, limit - len(items))
        return items[:limit]


def _with_manifest_source(item: ContextItem) -> ContextItem:
    metadata = {**item.metadata, "retrieval_source": "manifest"}
    return item.model_copy(update={"metadata": metadata})
