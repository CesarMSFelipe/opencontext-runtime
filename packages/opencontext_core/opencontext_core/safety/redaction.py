"""Centralized sink guard and redaction helpers."""

from __future__ import annotations

import re

from opencontext_core.safety.pii import BasicPiiScanner
from opencontext_core.safety.secrets import SecretScanner

# Inline env-style assignments anywhere in prose. Same name vocabulary as the
# core ENV_SECRET_RE, without the line-start anchor: free-form text (run tasks,
# memory notes) carries `NAME=value` mid-sentence, where the anchored pattern
# and the exact-length provider regexes both miss.
_INLINE_ENV_SECRET_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|API_KEY|PRIVATE_KEY|DATABASE_URL)"
    r"[A-Z0-9_]*\s*=\s*)([^\s#'\"]+)"
)


def _redact_inline_assignment(match: re.Match[str]) -> str:
    if match.group(2).startswith("[REDACTED"):
        return match.group(0)
    return f"{match.group(1)}[REDACTED:env_secret]"


def redact_prose_secrets(text: str) -> str:
    """Redact secrets from free-form prose before it reaches a persistent sink.

    Applies :meth:`SecretScanner.redact` plus an inline ``NAME=value`` pass so a
    token pasted mid-sentence (e.g. into a run task) never persists raw into run
    artifacts, session stores, or memory (PRODUCT_CONTRACT safety / AC-028).
    """
    if not text:
        return text
    redacted = SecretScanner().redact(text)
    return _INLINE_ENV_SECRET_RE.sub(_redact_inline_assignment, redacted)


class SinkGuard:
    """Applies conservative redaction before data reaches external sinks."""

    def __init__(self) -> None:
        self._secret_scanner = SecretScanner()
        self._pii_scanner = BasicPiiScanner()

    def redact(self, text: str) -> tuple[str, bool]:
        """Redact secrets and PII-like values from text."""

        secret_redacted = self._secret_scanner.redact(text)
        findings = self._pii_scanner.scan(secret_redacted)
        if not findings:
            return secret_redacted, secret_redacted != text
        chars = list(secret_redacted)
        for finding in reversed(findings):
            chars[finding.start : finding.end] = "[REDACTED:pii]"
        value = "".join(chars)
        return value, True
