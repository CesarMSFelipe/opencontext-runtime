"""Evidence and provenance models for OpenContext context contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class EvidenceRef(BaseModel):
    """Reference to a piece of evidence supporting a context decision."""

    source: str = Field(description="Origin identifier (file path, symbol, etc).")
    source_type: str = Field(description="Category of source (code, file, memory, graph).")
    confidence: float = Field(description="Confidence score in [0.0, 1.0].")
    verified: bool = Field(default=False, description="Whether this evidence has been verified.")

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0.0, 1.0], got {v}")
        return v
