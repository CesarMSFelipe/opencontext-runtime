"""IntentRecord model + deterministic, offline intent parsing.

`parse_intent` turns a raw product-level intent string into a structured
`IntentRecord` and maps it onto the architecture-book documents that govern it
(e.g. ``01``/``16``/``43``/``45``/``49``) so every downstream slice stays
traceable to a source document. Parsing is deterministic and never calls a
provider, so the program-coverage guarantee never depends on a model call.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC

# Architecture-book document ids this planner is allowed to reference.
KNOWN_ARCHITECTURE_DOCS: tuple[str, ...] = ("01", "16", "43", "45", "49")

# Keyword -> architecture-book doc id (deterministic, offline mapping).
_DOC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "01": ("architecture", "system", "runtime", "facade", "api", "substrate"),
    "16": ("roadmap", "milestone", "implementation", "phase", "schedule"),
    "43": ("backlog", "epic", "requirement", "task"),
    "45": ("convergence", "validation", "matrix", "coverage"),
    "49": ("sequencing", "acceptance", "gate", "release", "pr "),
}

_OUTCOME_MARKERS: tuple[str, ...] = (
    "so that",
    "so as",
    "deliver",
    "produce",
    "enable",
    "result",
    "success",
)
_CONSTRAINT_MARKERS: tuple[str, ...] = (
    "must",
    "without",
    "constraint",
    "additive",
    "deterministic",
    "offline",
    "no orphan",
    "reuse",
)


class IntentRecord(BaseModel):
    """A structured, typed record of a product-level intent."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.intent.v1"
    intent_id: str
    raw_text: str
    goal: str
    outcomes: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    referenced_docs: list[str] = Field(default_factory=list)
    created_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_doc_id(doc_id: str) -> str:
    """Reduce a doc reference (``01-system-architecture.md``) to its id (``01``)."""
    match = re.match(r"\s*(\d+)", doc_id)
    return match.group(1) if match else doc_id.strip()


def _sentences(raw_text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", raw_text.strip())
    return [p.strip() for p in parts if p.strip()]


def _extract_goal(raw_text: str) -> str:
    sentences = _sentences(raw_text)
    if sentences:
        return sentences[0]
    return raw_text.strip()


def _extract_clauses(raw_text: str, markers: tuple[str, ...]) -> list[str]:
    clauses: list[str] = []
    for sentence in _sentences(raw_text):
        lowered = sentence.lower()
        if any(marker in lowered for marker in markers):
            clauses.append(sentence)
    return clauses


def map_to_docs(raw_text: str, *, docs: Mapping[str, str] | None = None) -> list[str]:
    """Map intent text onto the architecture-book documents that govern it.

    Returns a non-empty, de-duplicated list of *known* architecture-book doc ids,
    preserving ``KNOWN_ARCHITECTURE_DOCS`` order. Falls back to ``01``
    (system architecture) when no keyword matches so every intent is traceable.
    """
    lowered = raw_text.lower()
    matched: list[str] = []
    for doc_id in KNOWN_ARCHITECTURE_DOCS:
        keywords = _DOC_KEYWORDS.get(doc_id, ())
        if any(keyword in lowered for keyword in keywords):
            matched.append(doc_id)

    if docs:
        for raw_id in docs:
            normalized = _normalize_doc_id(raw_id)
            if normalized in KNOWN_ARCHITECTURE_DOCS and normalized not in matched:
                matched.append(normalized)

    if not matched:
        matched.append("01")
    return matched


def parse_intent(raw_text: str, *, docs: Mapping[str, str] | None = None) -> IntentRecord:
    """Parse a raw intent string into a structured ``IntentRecord`` (offline)."""
    return IntentRecord(
        intent_id=f"intent-{uuid.uuid4().hex[:12]}",
        raw_text=raw_text,
        goal=_extract_goal(raw_text),
        outcomes=_extract_clauses(raw_text, _OUTCOME_MARKERS),
        constraints=_extract_clauses(raw_text, _CONSTRAINT_MARKERS),
        referenced_docs=map_to_docs(raw_text, docs=docs),
        created_at=_now(),
    )


__all__ = [
    "KNOWN_ARCHITECTURE_DOCS",
    "IntentRecord",
    "map_to_docs",
    "parse_intent",
]
