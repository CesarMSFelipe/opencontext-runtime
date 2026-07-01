"""KG v2 schema — 23 node types + 21 edge types + Pydantic models.

PR-008.a: L4-layer canonical schema. Every node and edge carries
a TemporalMetadata envelope for soft-deletion and audit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class KgNodeType(str, Enum):
    """23 node types covering code, infra, people, and runtime domains."""

    FILE = "file"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    IMPORT = "import"
    EXPORT = "export"

    API_ENDPOINT = "api_endpoint"
    ROUTE = "route"
    MIDDLEWARE = "middleware"

    CONFIG = "config"
    ENV_VAR = "env_var"
    SECRET = "secret"

    OWNER = "owner"
    TEAM = "team"
    CODEOWNER = "codeowner"

    TEST = "test"
    BENCHMARK = "benchmark"
    FIXTURE = "fixture"

    DEPENDENCY = "dependency"
    ARTIFACT = "artifact"
    DOCUMENT = "document"


class KgEdgeType(str, Enum):
    """21 edge types covering structural, call, data, and organizational flows."""

    CALLS = "calls"
    IMPLEMENTS = "implements"
    INHERITS = "inherits"
    IMPORTS = "imports"
    EXPORTS = "exports"
    DEPENDS_ON = "depends_on"
    REFERENCES = "references"

    BELONGS_TO = "belongs_to"
    CONTAINS = "contains"
    DECLARED_IN = "declared_in"

    OWNS = "owns"
    MAINTAINS = "maintains"
    REVIEWED_BY = "reviewed_by"
    AUTHORED_BY = "authored_by"

    TESTS = "tests"
    MOCKS = "mocks"
    VERIFIES = "verifies"

    SUPERSEDES = "supersedes"
    REPLACED_BY = "replaced_by"
    INVALIDATES = "invalidates"
    CONFLICTS_WITH = "conflicts_with"


class TemporalMetadata(BaseModel):
    """Soft-delete + audit envelope attached to every node and edge.

    ``superseded_at`` is the timestamp when a newer version replaced
    this record; None means the record is still the active version.
    """

    model_config = ConfigDict(extra="forbid")

    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    superseded_at: datetime | None = Field(default=None)
    source_commit: str | None = Field(default=None)
    source_author: str | None = Field(default=None)

    @property
    def is_active(self) -> bool:
        return self.superseded_at is None


class KgNode(BaseModel):
    """A node in the knowledge graph."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable node ID, e.g. n:function:my_func")
    type: KgNodeType = Field(description="One of 23 node types")
    name: str = Field(default="", description="Human-readable name")
    properties: dict[str, object] = Field(default_factory=dict)
    temporal: TemporalMetadata = Field(default_factory=TemporalMetadata)


class KgEdge(BaseModel):
    """A directed edge in the knowledge graph."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default="", description="Stable edge ID")
    type: KgEdgeType = Field(description="One of 21 edge types")
    source: str = Field(description="Source node ID")
    target: str = Field(description="Target node ID")
    properties: dict[str, object] = Field(default_factory=dict)
    temporal: TemporalMetadata = Field(default_factory=TemporalMetadata)


__all__ = [
    "KgEdge",
    "KgEdgeType",
    "KgNode",
    "KgNodeType",
    "TemporalMetadata",
]
