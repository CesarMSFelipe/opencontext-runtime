"""Protected span detection for safe compression."""

from __future__ import annotations

import re

from opencontext_core.models.context import ProtectedSpan

CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
JSON_SCHEMA_RE = re.compile(r"\{[^{}]*(?:\"\$schema\"|\"type\"\s*:\s*\"object\")[\s\S]*?\}")
FILE_PATH_RE = re.compile(r"\b(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\b")
NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?(?:%|ms|s|MB|GB|tokens?)?\b")
CITATION_RE = re.compile(r"(?:\[[0-9A-Za-z_.:-]+\]|\([A-Z][A-Za-z]+,\s*\d{4}\))")
# Constraint/warning triggers are matched INLINE (anywhere in the text), whole-word, so
# that a load-bearing constraint embedded mid-paragraph ("the API must never be called
# twice") is protected -- not only ones at the start of a line. Multi-word phrases allow
# flexible inter-word whitespace; \b boundaries avoid false positives (e.g. "nevertheless").
WARNING_RE = re.compile(
    r"\b(?:"
    r"must\s+not|must\s+never|do\s+not|shall\s+not|"
    r"never|required|forbidden|caution|warning|security|legal|medical"
    r")\b",
    re.IGNORECASE,
)


class ProtectedSpanManager:
    """Detects content that lossy compression must preserve."""

    def detect(self, content: str) -> list[ProtectedSpan]:
        """Return protected spans in deterministic order."""

        spans: list[ProtectedSpan] = []
        spans.extend(_find_spans(content, CODE_BLOCK_RE, "code_block"))
        spans.extend(_find_spans(content, JSON_SCHEMA_RE, "json_schema"))
        spans.extend(_find_spans(content, FILE_PATH_RE, "file_path"))
        spans.extend(_find_spans(content, NUMBER_RE, "numeric_value"))
        spans.extend(_find_spans(content, CITATION_RE, "citation"))
        spans.extend(_find_spans(content, WARNING_RE, "warning"))
        return _dedupe_overlaps(spans)

    def has_protected_spans(self, content: str) -> bool:
        """Return whether content has protected spans."""

        return bool(self.detect(content))


def _find_spans(content: str, pattern: re.Pattern[str], kind: str) -> list[ProtectedSpan]:
    return [
        ProtectedSpan(start=match.start(), end=match.end(), kind=kind, content=match.group(0))
        for match in pattern.finditer(content)
    ]


def _dedupe_overlaps(spans: list[ProtectedSpan]) -> list[ProtectedSpan]:
    ordered = sorted(spans, key=lambda span: (span.start, -(span.end - span.start), span.kind))
    result: list[ProtectedSpan] = []
    occupied_until = -1
    for span in ordered:
        if span.start < occupied_until:
            continue
        result.append(span)
        occupied_until = span.end
    return result
