"""Redaction for Studio v2 response payloads.

Applies two complementary passes at the response boundary:

1. **Key-name masking**: fields whose key is in ``_MASK_KEYS`` (``api_key``,
   ``secret``, ``token``) are unconditionally replaced with ``"***REDACTED***"``.
2. **Content-based masking**: all string *values* are passed through the core
   :func:`~opencontext_core.studio.redaction.redact_value` /
   :class:`~opencontext_core.safety.redaction.SinkGuard` pipeline, which
   detects secrets by pattern (AWS keys, bearer tokens, etc.) regardless of the
   field name they appear in.

This module delegates the content pass to
:mod:`opencontext_core.studio.redaction` so there is exactly **one** canonical
secret-detection implementation in the codebase.
"""

from __future__ import annotations

from typing import Any

_MASK_KEYS: frozenset[str] = frozenset({"api_key", "secret", "token"})


def mask(value: Any) -> Any:
    """Return a redacted copy of *value* with key-name and content-based masking.

    * Dict keys in ``_MASK_KEYS`` → ``"***REDACTED***"`` unconditionally.
    * String values → content-based SinkGuard pass (AWS keys, tokens, etc.).
    * Lists and nested dicts → recursed.
    """
    from opencontext_core.studio.redaction import redact_value as _core_redact

    if isinstance(value, dict):
        return {k: ("***REDACTED***" if k in _MASK_KEYS else mask(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [mask(item) for item in value]
    if isinstance(value, str):
        return _core_redact(value)
    return value


__all__ = ["mask"]
