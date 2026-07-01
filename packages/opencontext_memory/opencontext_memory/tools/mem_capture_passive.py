"""mem_capture_passive — extract bullets from a "Key Learnings" section.

REQ-OMT-011 — ``mem_capture_passive(content: str) -> list[str]``.

The heuristic is deliberately regex-only (no LLM): the section header
must be one of ``## Key Learnings:`` or ``## Aprendizajes Clave:``; the
extractor walks forward until the next ``## `` heading (or end-of-string)
and pulls every ``- foo`` bullet. Items may include nested ``  - ``
indentation; we strip the leading whitespace before returning.
"""

from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^##\s+(?:Key Learnings|Aprendizajes Clave)\s*:\s*$", re.MULTILINE)
_NEXT_HEADING_RE = re.compile(r"^##\s+", re.MULTILINE)
_BULLET_RE = re.compile(r"^[ \t]*-\s+(.*)$", re.MULTILINE)


def mem_capture_passive(
    content: str,
    *,
    session_id: str = "manual-save",
    source: str = "subagent-stop",
) -> list[str]:
    """Return the bullets under the first matching learnings section.

    Returns ``[]`` when no section header is found (per the spec's
    "no error" branch). ``session_id`` and ``source`` are accepted so
    the host can wire this through the same surface as ``mem_save``
    later, but they're stored only when the host calls ``mem_save`` on
    each returned bullet — the extractor itself is a pure parser.
    """
    del session_id, source
    heading = _HEADING_RE.search(content)
    if heading is None:
        return []
    start = heading.end()
    tail = content[start:]
    # Skip the trailing newline (and any blank lines) after the heading
    # so the first bullet lands at the start of a line for the regex.
    tail = tail.lstrip("\n").lstrip()
    # Stop at the next markdown heading.
    stop = _NEXT_HEADING_RE.search(tail)
    section = tail if stop is None else tail[: stop.start()]
    return [m.group(1).strip() for m in _BULLET_RE.finditer(section) if m.group(1).strip()]


__all__ = ["mem_capture_passive"]
