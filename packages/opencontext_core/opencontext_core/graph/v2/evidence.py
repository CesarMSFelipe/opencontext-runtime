from __future__ import annotations

"""KG v2 evidence contract — L0-level EvidenceRef that nodes/edges carry.

PR-008.a: every KgNode and KgEdge carries an optional EvidenceRef
pointing to the concrete source location that produced it.
"""


import hashlib
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvidenceRef(BaseModel):
    """L0 immutable evidence pointer — what file, where, when, commit."""

    model_config = ConfigDict(extra="forbid")

    source_path: str = Field(description="Filesystem path of the source file.")
    source_line: int = Field(default=0, ge=0, description="Line number, 0 when unknown.")
    source_column: int = Field(default=0, ge=0, description="Column, 0 when unknown.")
    source_commit: str | None = Field(default=None, description="Git commit SHA.")
    source_timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    content_hash: str = Field(default="", description="SHA-256 of the source content.")

    def model_post_init(self, _context: Any) -> None:
        if not self.content_hash and self.source_path:
            self.content_hash = new_kg_id(f"{self.source_path}:{self.source_line}".encode())


def new_kg_id(content: bytes | str) -> str:
    """Derive a stable KG id from content bytes (SHA-256 hex)."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()[:16]


__all__ = ["EvidenceRef", "new_kg_id"]
