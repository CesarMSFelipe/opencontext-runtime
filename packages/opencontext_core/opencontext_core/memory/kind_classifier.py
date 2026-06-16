"""Deterministic content -> memory-kind classifier.

A memory's storage *layer* is chosen by the writer, but its *intent* (is this a
decision? an error? a constraint?) is latent in the text. This derives that
intent with a small frozen table of high-precision regex rules — no model call,
no dependency, fully deterministic — so memory can be filtered by what it means
("show past decisions / errors"), not just by where it was stored.

Ranking is by the single strongest matched rule (not a sum), so one decisive
signal beats many weak ones; ties break on cumulative score then a canonical
priority. When no rule fires with enough confidence — or the text is too short
to judge — it falls back to ``FACT`` rather than guessing.
"""

from __future__ import annotations

import re

from opencontext_core.memory_usability.memory_candidates import MemoryKind

# (compiled regex, weight) per kind. Weights are hand-tuned so a decisive phrase
# (e.g. an exception class name) outranks a generic hint. Kept small and precise
# on purpose — a sprawling table rots and misfires.
_I = re.IGNORECASE
_RULES: dict[MemoryKind, list[tuple[re.Pattern[str], float]]] = {
    MemoryKind.ERROR: [
        (re.compile(r"(?-i:\b\w+(?:Error|Exception)\b)", _I), 5.0),  # ZeroDivisionError
        (re.compile(r"\btraceback\b|\bstack ?trace\b", _I), 4.0),
        (re.compile(r"\b(raised|threw|crashed|segfault)\b", _I), 3.0),
        (re.compile(r"\bfailed (?:with|because|due to)\b", _I), 3.0),
        (re.compile(r"\b(bug|broken|regression)\b", _I), 2.0),
    ],
    MemoryKind.DECISION: [
        (re.compile(r"\bdecision\s*:", _I), 5.0),
        (re.compile(r"\b(decided|chose|opted) to\b", _I), 4.0),
        (re.compile(r"\bwe(?:'ll| will| are going to)? (?:use|adopt|go with)\b", _I), 3.5),
        (re.compile(r"\b(instead of|rather than)\b.*\bbecause\b", _I), 3.0),
    ],
    MemoryKind.CONSTRAINT: [
        (re.compile(r"\b(must not|never|do not|don't|always)\b", _I), 4.0),
        (re.compile(r"\b(must|required to|has to|may not|cannot)\b", _I), 3.0),
        (re.compile(r"\b(constraint|invariant|policy|rule)\s*:", _I), 4.0),
    ],
    MemoryKind.VALIDATION: [
        (re.compile(r"\b(verified|validated|confirmed) that\b", _I), 4.0),
        (re.compile(r"\b(tests? (?:pass|passed|green)|all green)\b", _I), 4.0),
        (re.compile(r"\b(checked|asserted) that\b", _I), 3.0),
    ],
    MemoryKind.SUMMARY: [
        (re.compile(r"\b(in summary|to summarize|overall|tl;dr)\b", _I), 4.0),
        (re.compile(r"\bsummary\s*:", _I), 4.0),
    ],
}

# Tie-break order when two kinds match equally strongly (most specific first).
_PRIORITY: tuple[MemoryKind, ...] = (
    MemoryKind.ERROR,
    MemoryKind.DECISION,
    MemoryKind.CONSTRAINT,
    MemoryKind.VALIDATION,
    MemoryKind.SUMMARY,
    MemoryKind.FACT,
)

_MIN_WORDS = 3
_MIN_SIGNAL = 2.0


def classify_kind(content: str) -> MemoryKind:
    """Classify text into a :class:`MemoryKind`, defaulting to ``FACT``.

    Deterministic and dependency-free. Falls back to ``FACT`` when the text is
    too short or no rule matches strongly enough to be trusted.
    """
    text = (content or "").strip()
    if len(text.split()) < _MIN_WORDS:
        return MemoryKind.FACT

    strongest: dict[MemoryKind, float] = {}
    cumulative: dict[MemoryKind, float] = {}
    for kind, rules in _RULES.items():
        for pattern, weight in rules:
            if pattern.search(text):
                strongest[kind] = max(strongest.get(kind, 0.0), weight)
                cumulative[kind] = cumulative.get(kind, 0.0) + weight

    if not strongest:
        return MemoryKind.FACT
    best = max(strongest, key=lambda k: (strongest[k], cumulative[k], -_PRIORITY.index(k)))
    if strongest[best] < _MIN_SIGNAL:
        return MemoryKind.FACT
    return best
