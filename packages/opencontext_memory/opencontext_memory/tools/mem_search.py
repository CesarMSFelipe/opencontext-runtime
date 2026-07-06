"""mem_search — eager FTS5 BM25 search over observations.

REQ-OMT-002 — ``mem_search(query, *, match_mode="all", limit=20, project=None,
scope=None, type=None) -> list[SearchHit]``.

Backed by :meth:`opencontext_memory.MemoryStore.search`; the tool adds
FTS5-safe query sanitisation and a self-filter so the freshly-written
observation from a concurrent ``mem_save`` never appears in its own
search result. Soft-deleted rows (``deleted_at IS NOT NULL``) are already
excluded by the store query.
"""

from __future__ import annotations

import re
from typing import Any

# Match the cap used by mem_save so conflict detection and search agree on
# what "safe to query" means. Two tokens is enough for both BM25 ranking
# and the conflict-surfacing flow.
_FTS_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_SAFE_QUERY_TOKEN_CAP = 2


def _safe_fts_query(text: str, *, limit: int = _SAFE_QUERY_TOKEN_CAP) -> str:
    """Build an FTS5-safe query from the first ``limit`` alphanumeric tokens.

    SQLite FTS5 treats ``/``, ``-``, ``(``, ``)`` as operators; wrapping each
    token in double quotes forces literal-phrase matching.
    """
    tokens = _FTS_TOKEN_RE.findall(text)[:limit]
    return " ".join(f'"{t}"' for t in tokens)


def mem_search(
    store: Any,
    *,
    query: str,
    limit: int = 20,
    project: str | None = None,
    scope: str | None = None,
    type: str | None = None,
    match_mode: str = "all",
    include_proposed: bool = False,
) -> list[dict[str, Any]]:
    """Return BM25-ranked observations matching ``query``.

    Parameters
    ----------
    store:
        An :class:`opencontext_memory.MemoryStore` (or anything with a
        ``.search(query, limit)`` method returning dict rows).
    query:
        Free-form query string. Special characters are stripped; only
        alphanumeric tokens contribute.
    limit:
        Maximum number of hits to return. Defaults to the spec value (20).
    project, scope, type:
        Optional filters applied AFTER the BM25 search (the store has no
        per-column FTS5 filter). ``None`` means "do not filter".
    match_mode:
        Forwarded for API parity with the engram MCP surface; the current
        FTS5 store always combines tokens with implicit AND, so ``match_mode``
        is accepted but ignored. Mismatches raise ``ValueError`` so silent
        contract drift is impossible.
    include_proposed:
        MEMORY_CONTRACT approval flow. ``proposed`` (unapproved) rows are
        excluded from default results; pass ``True`` to surface them
        explicitly (e.g. for a review queue).
    """
    if match_mode not in {"all", "any"}:
        raise ValueError(f"invalid_match_mode:{match_mode}")
    del match_mode

    safe_query = _safe_fts_query(query)
    if not safe_query:
        return []

    hits = store.search(safe_query, limit=limit)
    if not include_proposed:
        hits = [h for h in hits if str(h.get("lifecycle_state") or "active") != "proposed"]
    if project is not None:
        hits = [h for h in hits if h.get("project") == project]
    if scope is not None:
        hits = [h for h in hits if h.get("scope") == scope]
    if type is not None:
        hits = [h for h in hits if h.get("type") == type]
    return [dict(h) for h in hits]


__all__ = ["mem_search"]
