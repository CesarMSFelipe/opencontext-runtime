"""Redaction pipeline (REQ-data-gov-002, PR-R2-B).

Runs **synchronously and before** any provider call. Every pattern in
``RedactionRule.pattern`` that matches a value in the input text is replaced
with a deterministic token of the form ``<REDACTED:<sha256-16hex>>`` so that:

1. The original secret never reaches the provider / network / log.
2. Auditors can dedupe redaction events (same secret → same tag) without ever
   seeing the secret itself.

The pipeline is the only entry point used by ``ProviderRedactionFilter``
(PR-012) and the ingest-time defense-in-depth pass (REQ-data-gov-002 §2).
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

__all__ = [
    "RedactionPipeline",
    "RedactionResult",
    "RedactionRule",
    "apply_redaction",
]

_REDACTED_PREFIX = "<REDACTED:"
_REDACTED_SUFFIX = ">"


def _redaction_tag(secret: str) -> str:
    """Return ``<REDACTED:<sha256-16hex>>`` for *secret* (deterministic)."""
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]
    return f"{_REDACTED_PREFIX}{digest}{_REDACTED_SUFFIX}"


@dataclass(frozen=True)
class RedactionRule:
    """A single named regex rule."""

    name: str
    pattern: re.Pattern[str]

    def apply(self, text: str) -> str:
        return self.pattern.sub(lambda m: _redaction_tag(m.group(0)), text)


@dataclass(frozen=True)
class RedactionResult:
    """The outcome of a :class:`RedactionPipeline.apply` call."""

    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def redacted(self) -> bool:
        return any(v > 0 for v in self.counts.values())


class RedactionPipeline:
    """Applies :class:`RedactionRule`s in order. First match wins per rule."""

    def __init__(self, rules: Sequence[RedactionRule] | Iterable[RedactionRule] = ()) -> None:
        self._rules: list[RedactionRule] = list(rules)

    @property
    def rules(self) -> tuple[RedactionRule, ...]:
        return tuple(self._rules)

    def apply(self, text: str) -> RedactionResult:
        if not self._rules:
            return RedactionResult(text=text, counts={})
        out = text
        counts: dict[str, int] = {}
        for rule in self._rules:
            rule_hits = sum(1 for _ in rule.pattern.finditer(out))
            if rule_hits:
                out = rule.apply(out)
                counts[rule.name] = counts.get(rule.name, 0) + rule_hits
        return RedactionResult(text=out, counts=counts)


def apply_redaction(text: str, rules: Sequence[RedactionRule] | Iterable[RedactionRule]) -> str:
    """Standalone convenience form — returns the redacted text only.

    For full counts / metadata use :meth:`RedactionPipeline.apply`.
    """
    return RedactionPipeline(rules).apply(text).text
