"""mem_save — the eager memory tool that every host agent calls.

REQ-OMT-001 — ``mem_save(title, content, type, **kwargs) -> SaveReceipt``.

The tool always returns ``{receipt, judgment_required, candidates}``. When
the BM25 floor is cleared by an existing observation, ``judgment_required``
is True and each candidate carries the ``judgment_id`` correlation handle
that :func:`mem_judge` (PR2.c) accepts.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_memory.conflict import (
    BM25_FLOOR_DEFAULT,
    CandidateEnvelope,
    build_envelope,
)
from opencontext_memory.store.relations import RelationVerbs
from opencontext_memory.store.relations import insert as insert_relation

_FTS_TOKEN_RE = __import__("re").compile(r"[A-Za-z0-9_]+")


def _safe_fts_query(text: str, *, limit: int = 2) -> str:
    """Return an FTS5-safe query built from the first ``limit`` alphanumeric tokens.

    SQLite FTS5 treats ``/``, ``-``, ``(``, ``)``, etc. as operators and raises
    ``fts5: syntax error`` when a user-supplied string happens to contain one.
    Wrapping each token in double quotes forces FTS5 to treat them as literal
    phrases; the default FTS5 NEAR/AND semantics combine them.

    The cap is small (2) because FTS5's default proximity search drops any
    document that does not contain *all* the tokens in a tight window. Two
    tokens are enough for conflict detection: a near-duplicate will share
    at least one noun/identifier, which is what we want to surface.
    """
    tokens = _FTS_TOKEN_RE.findall(text)[:limit]
    return " ".join(f'"{t}"' for t in tokens)


class ReceiptRecord(BaseModel):
    """The persisted portion of the SaveReceipt.

    Mirrors :class:`opencontext_memory.store.sqlite.ObservationWriteResult` but
    is owned by this module so the public shape (``receipt.id``,
    ``receipt.upserted``) stays stable regardless of any future refactor of
    the store internals. The ``title`` / ``content`` / ``type`` / ``project``
    fields are echoed back so callers don't need a follow-up
    ``mem_get_observation`` to confirm what landed.
    """

    model_config = ConfigDict(extra="forbid")

    id: int = Field(description="New or updated observation row id.")
    upserted: bool = Field(
        default=False, description="True when an existing topic_key row was updated in place."
    )
    deduplicated: bool = Field(
        default=False,
        description="True when an equal-content live row absorbed this save (id is the "
        "existing row).",
    )
    title: str = Field(description="Echoed from the save call.")
    content: str = Field(description="Echoed from the save call.")
    type: str = Field(default="mem_save", description="Echoed from the save call.")
    project: str | None = Field(default=None, description="Echoed from the save call.")


class SaveReceipt(BaseModel):
    """The full return shape of :func:`mem_save`."""

    model_config = ConfigDict(extra="forbid")

    receipt: ReceiptRecord
    judgment_required: bool
    candidates: list[CandidateEnvelope] = Field(default_factory=list)


def mem_save(
    store: Any,
    *,
    session_id: str,
    project: str | None,
    title: str,
    content: str,
    type: str = "mem_save",
    topic_key: str | None = None,
    bm25_floor: float = BM25_FLOOR_DEFAULT,
    capture_prompt: bool = True,
    proposed: bool = False,
) -> SaveReceipt:
    """Persist one observation and surface any BM25 conflict as candidates.

    Parameters
    ----------
    store:
        A :class:`opencontext_memory.MemoryStore` instance (or anything that
        satisfies the same surface — the tool only calls ``.write``,
        ``.search``, ``._connect``).
    session_id:
        Originating session id (required by the store schema).
    project:
        Owning project handle; ``None`` is allowed but disables project-
        scoped conflict matching for the new row.
    title:
        Short human-readable title.
    content:
        Observation body. Empty content raises ``ValueError("content_required")``
        (matches REQ-OMT-001's "save invalid → error" branch).
    type:
        Tool / channel that produced the row (``decision``, ``bugfix``,
        ``architecture``, …).
    topic_key:
        Optional upsert handle; ``None`` is the common case for the first
        write of a topic.
    bm25_floor:
        Override the default ``-2.0`` threshold for tighter / looser matches.
    capture_prompt:
        REQ-OCF-005 hook. The host agent normally sets this ``True`` so the
        prompt that triggered the save is recorded. Automated paths
        (``mem_capture_passive``, ``mem_session_summary``) flip it ``False``.
        The actual prompt capture lives in PR2.c when ``mem_save_prompt``
        lands; for now we only honour the parameter as a no-op.
    proposed:
        MEMORY_CONTRACT approval flow. ``True`` lands the row as
        ``lifecycle_state='proposed'`` — excluded from default search/recall
        until ``mem_approve`` promotes it to ``active`` (the approved default).
    """
    if not content:
        raise ValueError("content_required")
    # capture_prompt is recorded by the prompt layer (PR2.c); kept here so
    # the tool signature is stable across PRs.
    del capture_prompt

    # 0) MEMORY_CONTRACT rule 1: redaction runs BEFORE save — secrets never
    #    reach the store or the echoed receipt.
    from opencontext_memory.redaction import redact_memory_text

    title = redact_memory_text(title)
    content = redact_memory_text(content)

    # 0b) Dedupe by exact content (MEMORY_CONTRACT rule 6): an equal-content
    #     live row in the same project absorbs the save — the existing id is
    #     returned and no duplicate row or conflict envelope is produced.
    existing_id = _absorb_equal_content(store, project=project, content=content)
    if existing_id is not None:
        return SaveReceipt(
            receipt=ReceiptRecord(
                id=existing_id,
                upserted=False,
                deduplicated=True,
                title=title,
                content=content,
                type=type,
                project=project,
            ),
            judgment_required=False,
            candidates=[],
        )

    # 1) Persist the observation first so the new row's id is known for the
    #    relation insert path.
    new_id, upserted = _write_observation(
        store,
        session_id=session_id,
        project=project,
        title=title,
        content=content,
        obs_type=type,
        topic_key=topic_key,
        lifecycle_state="proposed" if proposed else "active",
    )

    # 2) BM25 search against the live store. Filter self so the freshly
    #    written row never counts as its own conflict. We prefer the title
    #    for the query (titles are short, descriptive, and rarely contain
    #    FTS5 special chars); fall back to a content snippet if the title
    #    is too short to discriminate.
    query_text = title if title else content[:60]
    raw_hits = store.search(_safe_fts_query(query_text), limit=10)
    raw_hits = [h for h in raw_hits if int(h["id"]) != new_id]
    # Map the store's ``rank`` alias to the conflict envelope's
    # ``bm25_score`` field name so the Pydantic model can validate cleanly.
    raw_hits = [
        {
            "id": int(h["id"]),
            "title": str(h.get("title", "")),
            "content": str(h.get("content", "")),
            "bm25_score": float(h["rank"]),
        }
        for h in raw_hits
    ]

    # 3) Build the envelope. Empty input → judgment_required=False.
    envelope = build_envelope(raw_hits, query=content[:120], floor=bm25_floor)

    # 4) Persist one pending relation row per surviving candidate so the
    #    caller can later resolve it via mem_judge(judgment_id, ...).
    if envelope.candidates:
        conn = store._conn
        for cand in envelope.candidates:
            insert_relation(
                conn,
                source_id=new_id,
                target_id=int(cand.id),
                verb=RelationVerbs.RELATED,
                status="pending",
                marked_by_actor="user",
                confidence=float(cand.bm25_score),
                judgment_id=cand.judgment_id,
            )

    return SaveReceipt(
        receipt=ReceiptRecord(
            id=new_id,
            upserted=bool(upserted),
            title=title,
            content=content,
            type=type,
            project=project,
        ),
        judgment_required=envelope.judgment_required,
        candidates=envelope.candidates,
    )


def _absorb_equal_content(store: Any, *, project: str | None, content: str) -> int | None:
    """Return the id of an equal-content live row in ``project``, bumping its
    ``duplicate_count``; ``None`` when no duplicate exists."""
    from opencontext_memory.store.sqlite import _utcnow_iso

    with store._connect() as conn:
        row = conn.execute(
            """
            SELECT id FROM observations
            WHERE content = ? AND deleted_at IS NULL
              AND (project = ? OR (project IS NULL AND ? IS NULL))
            ORDER BY id LIMIT 1
            """,
            (content, project, project),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE observations SET duplicate_count = duplicate_count + 1, updated_at = ? "
            "WHERE id = ?",
            (_utcnow_iso(), int(row["id"])),
        )
        return int(row["id"])


def _write_observation(
    store: Any,
    *,
    session_id: str,
    project: str | None,
    title: str,
    content: str,
    obs_type: str,
    topic_key: str | None,
    lifecycle_state: str = "active",
) -> tuple[int, bool]:
    """Insert (or upsert) the observation and return ``(id, upserted)``.

    Imports :class:`Observation` lazily so the tool module stays decoupled
    from the store's Pydantic surface; PR2.c tools can reuse the same pattern.
    """
    from opencontext_memory.store.sqlite import Observation

    obs = Observation(
        session_id=session_id,
        type=obs_type,
        title=title,
        content=content,
        project=project,
        topic_key=topic_key,
        lifecycle_state=lifecycle_state,
    )
    if topic_key is not None:
        # Probe the store to know whether this is an upsert. Cheap because
        # the store keeps the connection in-process; one SELECT is fine for
        # the common case of fresh inserts where topic_key is None.
        with store._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM observations WHERE topic_key = ? AND project = ? "
                "AND scope = ? AND deleted_at IS NULL",
                (topic_key, project, "project"),
            ).fetchone()
    else:
        existing = None
    new_id = store.write(obs)
    return new_id, bool(existing is not None and int(existing["id"]) == new_id)


__all__ = ["ReceiptRecord", "SaveReceipt", "mem_save"]
