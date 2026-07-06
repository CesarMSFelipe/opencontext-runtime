"""Redaction pass applied to observation text before persisting.

MEMORY_CONTRACT rule 1: no secrets are ever stored; redaction runs before
save. Reuses the conservative :class:`opencontext_core.safety.secrets.
SecretScanner` and adds one memory-specific pass: inline ``NAME=value``
secret assignments in prose (the core env-secret pattern is anchored to
line start, but memory content is free-form text).
"""

from __future__ import annotations

import re

from opencontext_core.safety.secrets import SecretScanner

# Inline env-style assignments anywhere in prose. Same name vocabulary as the
# core ENV_SECRET_RE, without the line-start anchor.
_INLINE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|API_KEY|PRIVATE_KEY|DATABASE_URL)"
    r"[A-Z0-9_]*\s*=\s*)([^\s#'\"]+)"
)


def _redact_assignment(match: re.Match[str]) -> str:
    if match.group(2).startswith("[REDACTED"):
        return match.group(0)
    return f"{match.group(1)}[REDACTED:env_secret]"


def redact_memory_text(text: str) -> str:
    """Return ``text`` with secret values replaced by ``[REDACTED:*]`` markers."""
    if not text:
        return text
    redacted = SecretScanner().redact(text)
    return _INLINE_ASSIGNMENT_RE.sub(_redact_assignment, redacted)


__all__ = ["redact_memory_text"]
