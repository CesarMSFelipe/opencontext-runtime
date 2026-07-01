"""mem_save_prompt — record the user's prompt that triggered a save.

REQ-OMT-006 — ``mem_save_prompt(content, *, project=None) -> SaveReceipt``.

The ``project`` parameter is OPTIONAL; when omitted, the project handle is
auto-detected via :func:`opencontext_memory.tools.mem_current_project.mem_current_project`
(which itself reads the cwd's git origin per REQ-OMPD-001 → REQ-OMT-007).

The actual storage path delegates to :func:`opencontext_memory.tools.mem_save.mem_save`
with ``type="prompt"`` and ``title="prompt:<first-line>"``. Reusing
``mem_save`` keeps the conflict-surfacing flow (BM25 candidates,
``judgment_required`` envelope, pending-relation inserts) consistent
across observation types.
"""

from __future__ import annotations

from typing import Any

from opencontext_memory.tools.mem_current_project import mem_current_project
from opencontext_memory.tools.mem_save import SaveReceipt, mem_save


def _prompt_title(content: str) -> str:
    """Derive a short title for a prompt observation.

    Uses the first non-empty line (truncated to 80 chars). Falls back to
    a constant when the prompt is empty / whitespace-only so the row
    still has a human-readable title.
    """
    first_line = next((ln.strip() for ln in content.splitlines() if ln.strip()), "")
    if not first_line:
        return "prompt"
    return f"prompt:{first_line[:80]}"


def mem_save_prompt(
    store: Any,
    *,
    session_id: str,
    content: str,
    project: str | None = None,
) -> SaveReceipt:
    """Persist ``content`` as a prompt observation.

    Parameters
    ----------
    store:
        An :class:`opencontext_memory.MemoryStore`.
    session_id:
        Originating session id (passed through to ``mem_save``).
    content:
        The user prompt text. Empty content raises
        ``ValueError("content_required")`` (delegated from ``mem_save``).
    project:
        Owning project handle. ``None`` triggers auto-detection via
        :func:`mem_current_project`. When auto-detection returns
        ``project=None`` (e.g. inside an ambiguous git layout) the
        save proceeds with ``project=None`` so the row stays
        project-agnostic.
    """
    if project is None:
        detection = mem_current_project()
        project = detection.project
    return mem_save(
        store=store,
        session_id=session_id,
        project=project,
        title=_prompt_title(content),
        content=content,
        type="prompt",
    )


__all__ = ["mem_save_prompt"]
