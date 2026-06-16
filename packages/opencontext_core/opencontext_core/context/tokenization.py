"""Accurate token counting with a safe heuristic fallback.

``count_tokens`` uses ``tiktoken`` when it is importable and falls back to the
character-based heuristic in :func:`estimate_tokens` otherwise. The module is
import-safe when ``tiktoken`` is absent and produces deterministic results.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from opencontext_core.context.budgeting import estimate_tokens

_DEFAULT_ENCODING = "cl100k_base"


@lru_cache(maxsize=1)
def _tiktoken_module() -> Any | None:
    """Return the imported ``tiktoken`` module, or ``None`` when unavailable."""

    try:
        import tiktoken  # type: ignore[import-not-found]
    except ImportError:
        return None
    return tiktoken


def accurate_tokenizer_available() -> bool:
    """Whether an accurate tokenizer backend (tiktoken) can be used."""

    return _tiktoken_module() is not None


@lru_cache(maxsize=32)
def _encoding_for(model: str | None) -> Any | None:
    """Resolve a tiktoken encoding for ``model``, falling back to a default.

    Returns ``None`` when tiktoken is unavailable so callers degrade to the
    heuristic. Unknown models never raise; they use the default encoding.
    """

    tiktoken = _tiktoken_module()
    if tiktoken is None:
        return None

    if model:
        try:
            return tiktoken.encoding_for_model(model)
        except (KeyError, ValueError):
            pass

    try:
        return tiktoken.get_encoding(_DEFAULT_ENCODING)
    except (KeyError, ValueError):
        return None


def count_tokens(text: str, model: str | None = None) -> int:
    """Count tokens in ``text`` accurately when possible, else heuristically.

    The accurate path uses tiktoken; any failure or absence degrades to the
    deterministic character-based heuristic so behaviour is always defined.
    Empty or whitespace-only text counts as zero tokens, matching the heuristic.
    """

    if not text.strip():
        return 0

    encoding = _encoding_for(model)
    if encoding is None:
        return estimate_tokens(text)

    try:
        return max(1, len(encoding.encode(text)))
    except Exception:
        return estimate_tokens(text)
