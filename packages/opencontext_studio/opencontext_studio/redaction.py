"""commit-012: redaction helper for the Studio FastAPI surface.

A small, focused utility used by the v2 endpoints to mask sensitive
keys in JSON responses. The masking is intentionally narrow (api_key /
secret / token) so it cannot accidentally shadow legitimate fields;
broader redaction lives in ``opencontext_core.safety.redaction``.
"""

from __future__ import annotations

from typing import Any

_MASK_KEYS = frozenset({"api_key", "secret", "token"})


def mask(value: Any) -> Any:
    """Return a redacted copy of *value* with sensitive keys masked."""
    if isinstance(value, dict):
        return {k: ("***REDACTED***" if k in _MASK_KEYS else mask(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [mask(item) for item in value]
    return value


__all__ = ["mask"]
