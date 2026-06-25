"""ArtifactRef — pointer to a stored artifact by ID and content hash (slice 4).

Wraps a small set of supported storage backends (local, engram, openspec, aicx)
so callers can reference an artifact without bundling its content. The hash
ties the reference to a specific byte sequence; ``required`` flags artifacts
whose absence should fail the run.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Backend = Literal["local", "engram", "openspec", "aicx"]


class ArtifactRef(BaseModel):
    """Reference to a stored artifact by ID, backend, path, and content hash."""

    key: str = Field(description="Stable artifact identifier within the run")
    backend: Backend = Field(description="Storage backend where the artifact lives")
    path: str = Field(description="Backend-relative path or pointer")
    hash: str = Field(description="Content hash for integrity verification")
    required: bool = Field(default=True, description="If True, missing artifact fails the run")
    full_content_required: bool = Field(
        default=False, description="If True, summary-only retrieval is insufficient"
    )


if __name__ == "__main__":
    # Self-check: round-trip + backend validation.
    ref = ArtifactRef(key="k", backend="local", path="p", hash="h", required=True)
    assert ref.backend == "local"
    try:
        ArtifactRef(key="k", backend="nope", path="p", hash="h", required=True)  # type: ignore[arg-type]
    except Exception:
        pass
    else:
        raise AssertionError("expected backend validation error")
    print("context/artifact_ref.py self-check passed.")
