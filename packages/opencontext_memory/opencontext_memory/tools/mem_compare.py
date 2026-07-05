"""mem_compare — persist a fixed-provenance verdict between two memories.

REQ-OMT-017 — ``mem_compare(a: int, b: int, *, relation, confidence,
reasoning, model=None) -> CompareResult``.

The verb is validated against the 7-verb :class:`RelationVerbs` enum.
Cross-project pairs are rejected with
``ValueError("cross_project_pair_rejected")`` and no row is inserted.
The :func:`opencontext_memory.store.relations.JudgeBySemantic` helper
sets ``marked_by_actor='engram'`` (fixed) so a caller can never spoof
the provenance.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from opencontext_memory.store.relations import JudgeBySemantic, RelationVerbs


class CompareResult(BaseModel):
    """Return value of :func:`mem_compare`.

    Mirrors the spec's ``CompareResult`` Pydantic model so a FastAPI
    caller gets a stable JSON shape.
    """

    model_config = ConfigDict(extra="forbid")

    relation_id: int
    source_id: int
    target_id: int
    relation: str
    marked_by_actor: str = "engram"


def mem_compare(
    store: Any,
    *,
    memory_id_a: int,
    memory_id_b: int,
    relation: str,
    confidence: float,
    reasoning: str,
    model: str | None = None,
) -> CompareResult:
    """Insert a semantic verdict between ``memory_id_a`` and ``memory_id_b``.

    Cross-project pairs raise BEFORE any row is written. The verdict
    itself is inserted with ``marked_by_actor='engram'`` (cannot be
    overridden by the caller — that's the whole point of the
    ``JudgeBySemantic`` helper).
    """
    with store._connect() as conn:
        rows = conn.execute(
            """
            SELECT id, project FROM observations
            WHERE id IN (?, ?) AND deleted_at IS NULL
            """,
            (int(memory_id_a), int(memory_id_b)),
        ).fetchall()
        if len(rows) != 2:
            raise ValueError(f"memory_not_found:{(memory_id_a, memory_id_b)}")
        projects = {r["project"] for r in rows}
        if len(projects) > 1:
            raise ValueError("cross_project_pair_rejected")
        relation_id = JudgeBySemantic(
            conn,
            source_id=int(memory_id_a),
            target_id=int(memory_id_b),
            verb=relation,
            confidence=float(confidence),
            reasoning=reasoning,
            model=str(model) if model is not None else "",
        )

    return CompareResult(
        relation_id=int(relation_id),
        source_id=int(memory_id_a),
        target_id=int(memory_id_b),
        relation=str(relation),
        marked_by_actor="engram",
    )


__all__ = ["CompareResult", "RelationVerbs", "mem_compare"]
