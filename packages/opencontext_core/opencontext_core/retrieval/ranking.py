"""Retrieval scoring helpers for keyword, path, and symbol search."""

from __future__ import annotations

import re

from opencontext_core.models.project import FileKind, ProjectFile, Symbol

# CAMEL_RE tokenizes queries; underscores are stripped here then re-split by _split_camel
CAMEL_RE = re.compile(r"[A-Za-z0-9]+")
QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "does",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "of",
    "on",
    "project",
    "the",
    "this",
    "to",
    "with",
    "work",
}


def _split_camel(term: str) -> list[str]:
    """Split CamelCase into lowercase parts (e.g. PrivacyGate → ['privacy', 'gate'])."""
    parts: list[str] = []
    start = 0
    for i, char in enumerate(term):
        if i > 0 and char.isupper():
            parts.append(term[start:i].lower())
            start = i
    if start < len(term):
        parts.append(term[start:].lower())
    return [p for p in parts if len(p) > 1]


class RetrievalScorer:
    """Scores manifest entries with simple deterministic hybrid relevance."""

    def terms(self, query: str) -> list[str]:
        """Tokenize a query into lowercase terms, splitting CamelCase compounds.

        Skips: stopwords, single chars, and purely numeric terms (which would
        create spurious substring matches in symbol names via _hit_count).
        """

        raw_terms = CAMEL_RE.findall(query)
        terms: list[str] = []
        for raw_term in raw_terms:
            term = raw_term.lower()
            # Skip single-char, stopwords, and purely numeric terms
            if len(term) <= 1 or term in QUERY_STOPWORDS:
                continue
            if term.isdigit():
                continue
            # Split CamelCase compounds so PrivacyGate → privacy, gate
            split_parts = _split_camel(raw_term)
            for part in split_parts:
                if part not in QUERY_STOPWORDS:
                    terms.append(part)
                # Also add -ing stems for verbs
                if part.endswith("ing") and len(part) > 5:
                    stem = part[:-3]
                    if stem and stem not in QUERY_STOPWORDS:
                        terms.append(stem)
        return list(dict.fromkeys(terms))

    def file_score(
        self,
        terms: list[str],
        file: ProjectFile,
        symbols: list[Symbol],
    ) -> tuple[float, dict[str, object]]:
        """Score one file from keyword, path, symbol, and file-type signals."""

        haystacks = {
            "path": file.path.lower(),
            "summary": file.summary.lower(),
            "symbols": " ".join(symbol.name.lower() for symbol in symbols),
            "file_type": file.file_type.value,
        }
        path_hits = _hit_count(terms, haystacks["path"])
        summary_hits = _hit_count(terms, haystacks["summary"])
        symbol_hits = _hit_count(terms, haystacks["symbols"])
        type_hits = _hit_count(terms, haystacks["file_type"])
        raw = path_hits * 2.0 + summary_hits + symbol_hits * 3.0 + type_hits
        raw += _file_type_bonus(file.file_type)
        denominator = max(1.0, len(terms) * 4.0)
        score = min(1.0, raw / denominator)
        return score, {
            "path_hits": path_hits,
            "summary_hits": summary_hits,
            "symbol_hits": symbol_hits,
            "type_hits": type_hits,
        }

    def symbol_score(self, terms: list[str], symbol: Symbol) -> tuple[float, dict[str, object]]:
        """Score one symbol from name, kind, and path signals."""

        name_hits = _hit_count(terms, symbol.name.lower())
        kind_hits = _hit_count(terms, symbol.kind.lower())
        path_hits = _hit_count(terms, symbol.path.lower())
        raw = name_hits * 3.0 + kind_hits + path_hits
        denominator = max(1.0, len(terms) * 4.0)
        score = min(1.0, raw / denominator)
        return score, {"name_hits": name_hits, "kind_hits": kind_hits, "path_hits": path_hits}


def _hit_count(terms: list[str], haystack: str) -> int:
    return sum(1 for term in terms if term in haystack)


def _file_type_bonus(file_type: FileKind) -> float:
    bonuses = {
        FileKind.CODE: 0.2,
        FileKind.CONFIG: 0.16,
        FileKind.DOCUMENTATION: 0.12,
        FileKind.TEMPLATE: 0.1,
        FileKind.TEST: 0.08,
        FileKind.UNKNOWN: 0.02,
        FileKind.ASSET: 0.0,
    }
    return bonuses[file_type]
