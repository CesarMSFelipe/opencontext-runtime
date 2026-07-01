"""KG v2 incremental Tree-Sitter indexer.

PR-008.b: computes deltas from file-system changes, respecting a
token budget ceiling. Languages module provides per-language grammars.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IndexOptions:
    max_tokens: int = 3000
    budget_mode: str = "warn"  # warn | strict | off
    include_symbols: bool = True
    include_edges: bool = True


@dataclass
class IndexResult:
    nodes_found: int = 0
    edges_found: int = 0
    tokens_used: int = 0
    budget_exceeded: bool = False


@dataclass
class GraphDelta:
    added: set[str] = field(default_factory=set)
    modified: set[str] = field(default_factory=set)
    deleted: set[str] = field(default_factory=set)

    @property
    def added_count(self) -> int:
        return len(self.added)

    @property
    def modified_count(self) -> int:
        return len(self.modified)

    @property
    def deleted_count(self) -> int:
        return len(self.deleted)

    @property
    def total_changes(self) -> int:
        return self.added_count + self.modified_count + self.deleted_count


class IncrementalIndexer:
    """Computes index deltas from file-system changes.

    Accepts three sets of file paths (added, modified, deleted) and
    returns a GraphDelta with counts. The heavy parsing (Tree-Sitter)
    is deferred to the languages module.
    """

    def compute_delta(
        self,
        added: set[str] | None = None,
        modified: set[str] | None = None,
        deleted: set[str] | None = None,
    ) -> GraphDelta:
        return GraphDelta(
            added=added or set(),
            modified=modified or set(),
            deleted=deleted or set(),
        )


__all__ = [
    "GraphDelta",
    "IncrementalIndexer",
    "IndexOptions",
    "IndexResult",
]
