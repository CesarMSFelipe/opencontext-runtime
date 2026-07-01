"""Evidence and provenance models for OpenContext context contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# OC-KG-001 §11 source categories. ``source_type`` stays a plain ``str`` (not a
# ``Literal``) for backward compatibility — legacy callers pass values such as
# "code"/"graph"/"symbol" — but the v2 vocabulary is published here and enforced
# by ``EvidenceRef.is_kg_v2_source_type`` for KG v2 facts.
EVIDENCE_SOURCE_TYPES: tuple[str, ...] = (
    "file",
    "run",
    "commit",
    "artifact",
    "memory",
    "user",
    "tool",
)


class EvidenceRef(BaseModel):
    """Reference to a piece of evidence supporting a context decision.

    Extended for PR-008 KG v2 (OC-KG-001 §11): a fact's provenance can pin an
    exact ``path``/``line_start``/``line_end`` and the ``run_id`` that observed it.
    All v2 fields are optional so every pre-v2 ``EvidenceRef`` keeps validating
    unchanged; ``source``/``verified`` are retained for backward compatibility.
    """

    source: str = Field(description="Origin identifier (file path, symbol, etc).")
    source_type: str = Field(description="Category of source (code, file, memory, graph).")
    confidence: float = Field(description="Confidence score in [0.0, 1.0].")
    verified: bool = Field(default=False, description="Whether this evidence has been verified.")

    # --- KG v2 provenance (OC-KG-001 §11), all optional/back-compatible --------
    source_id: str | None = Field(
        default=None, description="Stable id of the source entity (run/commit/artifact/...)."
    )
    path: str | None = Field(default=None, description="Project-relative path of the evidence.")
    line_start: int | None = Field(default=None, description="First line of the evidence span.")
    line_end: int | None = Field(default=None, description="Last line of the evidence span.")
    run_id: str | None = Field(
        default=None, description="Run id that observed this evidence, when applicable."
    )

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0.0, 1.0], got {v}")
        return v

    def is_kg_v2_source_type(self) -> bool:
        """True when ``source_type`` is one of the OC-KG-001 §11 v2 categories."""
        return self.source_type in EVIDENCE_SOURCE_TYPES


# ---------------------------------------------------------------------------
# PR-008.a: re-export from graph.v2.evidence for backward compatibility
# ---------------------------------------------------------------------------


def EvidenceRef_v2(**kwargs: object) -> object:
    """Re-export shim — delegates to ``graph.v2.evidence.EvidenceRef``.

    Existing callers that import from ``models.evidence`` can still access
    the new L0 contract without changing their import path.
    """
    from opencontext_core.graph.v2.evidence import EvidenceRef

    return EvidenceRef(**kwargs)  # type: ignore[arg-type]
