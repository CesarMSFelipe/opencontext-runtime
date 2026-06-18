"""Efficient compression — maximum token reduction combining all strategies."""

from __future__ import annotations

from opencontext_core.backends.compression.compact import CompactCompressionBackend
from opencontext_core.backends.compression.terse import TerseCompressionBackend
from opencontext_core.models.context import ProtectedSpan

# Extended substitution dict beyond what terse already has
EXTENDED_DICT: dict[str, str] = {
    "function": "fn",
    "implementation": "impl",
    "interface": "iface",
    "module": "mod",
    "package": "pkg",
    "component": "comp",
    "service": "svc",
    "variable": "var",
    "constant": "const",
    "structure": "struct",
    "reference": "ref",
    "definition": "def",
    "declaration": "decl",
    "instantiation": "init",
    "therefore": "∴",
    "because": "∵",
    "does not": "≠",
    "greater than": ">",
    "less than": "<",
    "and": "&",
    "or": "|",
    "not": "¬",
    "input": "in",
    "output": "out",
    "result": "res",
    "response": "resp",
    "request": "req",
    "handler": "h",
    "callback": "cb",
    "timeout": "t/o",
    "connection": "conn",
    "transaction": "tx",
    "annotation": "ann",
}


class EfficientCompressionBackend:
    """Maximum compression: compact (code) + terse (prose) + extended dict.

    Order of operations:
    1. Compact: reduce code blocks to signatures
    2. Terse: compress prose (removes hedging, applies base dict)
    3. Extended dict: substitute remaining verbose terms
    Protected spans always preserved verbatim.
    """

    name = "efficient"

    def __init__(self) -> None:
        self._compact = CompactCompressionBackend()
        self._terse = TerseCompressionBackend()

    def compress(self, text: str, protected_spans: list[ProtectedSpan]) -> str:
        if not text:
            return text
        result = self._compact.compress(text, protected_spans)
        result = self._terse.compress(result, protected_spans)
        import re

        for verbose, concise in EXTENDED_DICT.items():
            pattern = r"\b" + re.escape(verbose) + r"\b"
            result = re.sub(pattern, concise, result, flags=re.IGNORECASE)
        return result
