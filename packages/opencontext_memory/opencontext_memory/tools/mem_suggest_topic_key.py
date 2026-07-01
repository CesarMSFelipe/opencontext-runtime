"""mem_suggest_topic_key — derive a deterministic ``topic_key`` slug.

REQ-OMT-010 — ``mem_suggest_topic_key(*, title, content='', type='manual') -> str``.

Pure function. Same input → same slug, every host, every session. The
slug format ``<type>/<kebab-title>`` matches what ``mem_save`` /
``Observation.topic_key`` already accept, so the host can round-trip a
suggestion through ``mem_save`` without further transformation.
"""

from __future__ import annotations

import re

_TITLE_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_NON_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slug_from_title(title: str) -> str:
    """Convert a free-form title into a kebab-case slug.

    Whitespace and punctuation collapse into single hyphens; runs of
    hyphens get squashed so the slug never contains ``--``. Empty input
    yields ``"untitled"`` so the function always returns a usable key.
    """
    tokens = _TITLE_TOKEN_RE.findall(title.lower())
    if not tokens:
        return "untitled"
    raw = "-".join(tokens)
    squashed = _NON_SLUG_RE.sub("-", raw).strip("-")
    return squashed or "untitled"


def mem_suggest_topic_key(*, title: str, content: str = "", type: str = "manual") -> str:
    """Return ``<type>/<kebab-title>``.

    ``content`` is accepted for API parity with the engram MCP surface
    but intentionally unused — the spec pins the slug to the title.
    """
    del content
    return f"{type}/{_slug_from_title(title)}"


__all__ = ["mem_suggest_topic_key"]
