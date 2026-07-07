"""Protected span detection for safe compression.

Signature-protection default (CTX-PROTECTED-LIST decision): the semantic KEEP
detectors — signatures, imports, relevant configuration, recent changes, recent
decisions, acceptance criteria, diagnostics, evidence — stay OPT-IN via
``include_semantic`` (the v2 Context Engine passes ``semantic_protection=True``).
The legacy default engine's byte-identical behavior is a pinned compatibility
contract (``test_legacy_compression_unchanged_without_semantic_protection``);
the v2 engine path is the surface that honors the full DOC2 §13.4 list.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

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

# --- PR-010 §Semantic Compression KEEP detectors (opt-in via include_semantic) ---
# These mark the book's KEEP categories that are NOT load-bearing constraints:
# acceptance criteria, code signatures, diagnostics, and evidence markers. They are
# opt-in so legacy compression behaviour stays byte-identical; only the v2 Context
# Engine path enables them, where "keep signatures/diagnostics verbatim" is intended.
ACCEPTANCE_RE = re.compile(
    r"^\s*(?:"
    r"-\s*\[[ xX]\]\s+"  # markdown checklist item
    r"|(?:GIVEN|WHEN|THEN)\b"  # gherkin acceptance scenario
    r"|AC\d*\s*:"  # AC:, AC1: ... acceptance-criterion label
    r"|acceptance criteria"  # literal heading
    r").*$",
    re.IGNORECASE | re.MULTILINE,
)
SIGNATURE_RE = re.compile(
    r"^\s*(?:async\s+)?(?:def|class|func|function|fn)\s+[A-Za-z_]\w*[^\n]*",
    re.MULTILINE,
)
DIAGNOSTIC_RE = re.compile(
    r"(?:Traceback \(most recent call last\)"
    r'|^\s*File "[^"]+", line \d+'
    r"|\b[A-Za-z_]*(?:Error|Exception)\b\s*:"
    r"|\bAssertionError\b)",
    re.MULTILINE,
)
EVIDENCE_MARKER_RE = re.compile(r"^\s*evidence\s*:\s*\S.*$", re.IGNORECASE | re.MULTILINE)

# --- CTX-PROTECTED-LIST detectors (DOC2 §13.4) — semantic KEEP path only ------
# Imports: Python (import / from-import), JS/TS (import ... from), CommonJS
# require, C/C++ #include, Rust use. Whole-line matches.
IMPORT_RE = re.compile(
    r"^[ \t]*(?:"
    r"from[ \t]+[\w.]+[ \t]+import[ \t]+[^\n]+"
    r"|import[ \t]+[^\n]+"
    r"|(?:const|let|var)[ \t]+[^\n=]+=[ \t]*require\(['\"][^'\"\n]+['\"]\)[^\n]*"
    r"|#include[ \t]*[<\"][^>\"\n]+[>\"]"
    r"|use[ \t]+[\w:]+[^\n]*;"
    r")$",
    re.MULTILINE,
)
# Relevant/effective configuration: env-style UPPER_CASE assignments (optionally
# exported) and ini/toml section headers. Conservative on purpose — ordinary
# lowercase code assignments are NOT configuration.
CONFIGURATION_RE = re.compile(
    r"^[ \t]*(?:"
    r"(?:export[ \t]+)?[A-Z][A-Z0-9_]{2,}[ \t]*[=:][ \t]*\S[^\n]*"
    r"|\[[\w.:\-]+\][ \t]*"
    r")$",
    re.MULTILINE,
)
# Recent changes: unified-diff fragments (diff/index/---/+++ headers and @@ hunks)
# are how recent changes appear inside packed context.
RECENT_CHANGE_RE = re.compile(
    r"^(?:"
    r"diff --git[^\n]*"
    r"|index [0-9a-f]+\.\.[0-9a-f]+[^\n]*"
    r"|(?:---|\+\+\+) [^\n]+"
    r"|@@[^\n]*@@[^\n]*"
    r")$",
    re.MULTILINE,
)
# Recent decisions: decision/ADR marker lines (headings or inline labels).
RECENT_DECISION_RE = re.compile(
    r"^[ \t]*(?:#+[ \t]*)?(?:decision(?:s)?\b[^\n]*:|decided\b|adr[- ]?\d+\b)[^\n]*$",
    re.IGNORECASE | re.MULTILINE,
)


class ProtectedSpanManager:
    """Detects content that lossy compression must preserve."""

    def detect(
        self,
        content: str,
        *,
        include_semantic: bool = False,
        referenced_fragments: Iterable[str] | None = None,
    ) -> list[ProtectedSpan]:
        """Return protected spans in deterministic order.

        When ``include_semantic`` is true (PR-010 Context Engine path), the book's
        KEEP categories — acceptance criteria, signatures, diagnostics, evidence,
        plus the DOC2 §13.4 imports/configuration/recent-change/recent-decision
        kinds — are also detected so the compression engine refuses to
        lossy-compress them. ``referenced_fragments`` optionally protects exact
        fragments referenced by memory or the KG (CTX-PROTECTED-LIST). Both
        default off so legacy callers are byte-identical.
        """

        spans: list[ProtectedSpan] = []
        spans.extend(_find_spans(content, CODE_BLOCK_RE, "code_block"))
        spans.extend(_find_spans(content, JSON_SCHEMA_RE, "json_schema"))
        spans.extend(_find_spans(content, FILE_PATH_RE, "file_path"))
        spans.extend(_find_spans(content, NUMBER_RE, "numeric_value"))
        spans.extend(_find_spans(content, CITATION_RE, "citation"))
        spans.extend(_find_spans(content, WARNING_RE, "warning"))
        if include_semantic:
            spans.extend(self.detect_semantic_keep(content))
        if referenced_fragments is not None:
            spans.extend(self.detect_referenced_fragments(content, referenced_fragments))
        return _dedupe_overlaps(spans)

    def detect_semantic_keep(self, content: str) -> list[ProtectedSpan]:
        """Return the semantic KEEP spans (PR-010 + CTX-PROTECTED-LIST kinds)."""

        spans: list[ProtectedSpan] = []
        spans.extend(_find_spans(content, ACCEPTANCE_RE, "acceptance_criteria"))
        spans.extend(_find_spans(content, SIGNATURE_RE, "signature"))
        spans.extend(_find_spans(content, DIAGNOSTIC_RE, "diagnostic"))
        spans.extend(_find_spans(content, EVIDENCE_MARKER_RE, "evidence"))
        spans.extend(_find_spans(content, IMPORT_RE, "import"))
        spans.extend(_find_spans(content, CONFIGURATION_RE, "configuration"))
        spans.extend(_find_spans(content, RECENT_CHANGE_RE, "recent_change"))
        spans.extend(_find_spans(content, RECENT_DECISION_RE, "recent_decision"))
        return _dedupe_overlaps(spans)

    def detect_referenced_fragments(
        self, content: str, fragments: Iterable[str]
    ) -> list[ProtectedSpan]:
        """Protect exact occurrences of memory/KG-referenced fragments (DOC2 §13.4).

        ``fragments`` are strings referenced by memory records or KG nodes (symbol
        names, keys, snippets). Every literal occurrence in ``content`` becomes a
        ``referenced_fragment`` span. Fragments shorter than 3 characters are
        skipped so single letters never lock whole documents.
        """

        spans: list[ProtectedSpan] = []
        for fragment in fragments:
            literal = str(fragment).strip()
            if len(literal) < 3:
                continue
            for match in re.finditer(re.escape(literal), content):
                spans.append(
                    ProtectedSpan(
                        start=match.start(),
                        end=match.end(),
                        kind="referenced_fragment",
                        content=match.group(0),
                    )
                )
        return _dedupe_overlaps(spans)

    def has_protected_spans(self, content: str, *, include_semantic: bool = False) -> bool:
        """Return whether content has protected spans."""

        return bool(self.detect(content, include_semantic=include_semantic))


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
