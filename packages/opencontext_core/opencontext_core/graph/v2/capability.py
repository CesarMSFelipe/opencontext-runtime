"""KG v2 capability + owner graph — PR-008.d."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CapabilityNode:
    id: str
    name: str
    tags: list[str] = field(default_factory=list)


@dataclass
class CapabilityGraph:
    nodes: list[CapabilityNode] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class OwnerRef:
    path: str
    owner: str
    source: str  # CODEOWNERS | git-log | unknown


class OwnerResolver:
    """Resolve ownership from CODEOWNERS, git-log, or emit unknown event."""

    def resolve(self, file_path: str) -> OwnerRef:
        # ponytail: stub — full resolution in PR-008.e
        return OwnerRef(path=file_path, owner="unknown", source="unknown")
