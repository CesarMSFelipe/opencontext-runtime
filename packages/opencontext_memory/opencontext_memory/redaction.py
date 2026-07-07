"""Redaction pass applied to observation text before persisting.

MEMORY_CONTRACT rule 1: no secrets are ever stored; redaction runs before
save. Delegates to the shared prose pass in
:mod:`opencontext_core.safety.redaction` (conservative ``SecretScanner`` plus
inline ``NAME=value`` assignments — memory content is free-form text, so the
line-anchored core env-secret pattern alone is not enough).
"""

from __future__ import annotations

from opencontext_core.safety.redaction import redact_prose_secrets


def redact_memory_text(text: str) -> str:
    """Return ``text`` with secret values replaced by ``[REDACTED:*]`` markers."""
    return redact_prose_secrets(text)


__all__ = ["redact_memory_text"]
