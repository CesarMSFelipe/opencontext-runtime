"""mem_judge — close the conflict loop on a pending relation row.

REQ-OMT-016 — ``mem_judge(judgment_id, relation, *, confidence=1.0,
reason=None, evidence=None) -> RelationRow``.

Validates the verb against the 7-verb :class:`RelationVerbs` enum (any
other value raises ``ValueError("invalid_relation_verb:<verb>")``) and
sets ``judgment_status='judged'`` on the matching row.
"""

from __future__ import annotations

from typing import Any

from opencontext_memory.store.relations import (
    RelationRow,
    RelationVerbs,
    fetch_by_judgment_id,
    update_judgment,
)


def mem_judge(
    store: Any,
    *,
    judgment_id: str,
    relation: str,
    confidence: float = 1.0,
    reason: str | None = None,
    evidence: str | None = None,
) -> RelationRow:
    """Promote a pending relation row to ``judgment_status='judged'``.

    Unknown ``relation`` values raise before any SQL runs so a typo can
    never silently persist as a bogus verb. ``evidence`` is accepted for
    API parity with the engram MCP surface but persisted via ``reason``
    (the ``reasoning`` column).
    """
    del evidence
    with store._connect() as conn:
        # update_judgment validates the verb and raises
        # ``invalid_relation_verb:<x>`` on a typo, BEFORE any SQL runs.
        update_judgment(
            conn,
            judgment_id=judgment_id,
            relation=relation,
            confidence=confidence,
            reasoning=reason,
        )
        row = fetch_by_judgment_id(conn, judgment_id)
    if row is None:
        # update_judgment is a no-op when no row matches — surface that
        # distinctly so the host can tell "typo'd a verb" from "typo'd an id".
        raise LookupError(f"judgment_not_found:{judgment_id}")
    return RelationRow.model_validate(row)


__all__ = ["RelationVerbs", "mem_judge"]
