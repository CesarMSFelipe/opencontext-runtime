"""Redaction for Studio payloads (SPEC-STU-014-11).

Every value Studio renders passes through the shared ``safety.redaction.SinkGuard``
so a classified secret is redacted before display. This walks JSON-able
structures (the ``model_dump`` of a view model) and redacts every string leaf,
reusing the one canonical redaction path rather than re-implementing it.
"""

from __future__ import annotations

from typing import Any

from opencontext_core.safety.redaction import SinkGuard

_GUARD = SinkGuard()


def redact_value(value: Any) -> Any:
    """Recursively redact secrets/PII from a JSON-able value."""

    if isinstance(value, str):
        safe, _ = _GUARD.redact(value)
        return safe
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(item) for item in value]
    return value
