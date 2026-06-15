"""Compact compression backend — structural summaries for Python code."""

from __future__ import annotations

import re

from opencontext_core.compression.terse import TerseCompressor
from opencontext_core.models.context import ProtectedSpan

_FENCED_CODE = re.compile(r"(```(?:python)?\n)(.*?)(```)", re.DOTALL)
_DEF_OR_CLASS = re.compile(
    r"^([ \t]*(?:@[\w.]+(?:\(.*?\))?\n[ \t]*)*(?:async\s+)?(?:def|class)\s+\w+[^\n]*:)[ \t]*\n"
    r"(?:[ \t]+\"\"\"(.*?)\"\"\"[ \t]*\n)?",
    re.MULTILINE | re.DOTALL,
)


_SIG_START = re.compile(r"(@|(?:async\s+)?(?:def|class)\s)")


def _compact_python_block(code: str) -> str:
    """Replace function/class bodies with signature + first docstring line only.

    Statement bodies are dropped and replaced with an ``...`` placeholder, but
    nested ``def``/``class`` signatures are preserved (the outer loop re-processes
    them), so a class collapses to its method signatures rather than vanishing.
    """
    lines = code.splitlines(keepends=True)
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        # Detect decorator or def/class line
        if _SIG_START.match(stripped):
            sig_indent = len(line) - len(line.lstrip())
            # Collect decorator+signature block
            sig_lines: list[str] = []
            while i < len(lines):
                sig_lines.append(lines[i])
                if lines[i].rstrip().endswith(":"):
                    i += 1
                    break
                i += 1
            result.extend(sig_lines)
            body_indent = sig_indent + 4
            # Optionally capture first docstring line
            if i < len(lines) and lines[i].lstrip().startswith('"""'):
                body_indent = len(lines[i]) - len(lines[i].lstrip())
                doc_line = lines[i].strip().removeprefix('"""').removesuffix('"""').strip()
                result.append(lines[i].split('"""')[0] + '"""' + doc_line + '..."""\n')
                # Skip rest of docstring
                if '"""' in lines[i][lines[i].index('"""') + 3 :]:
                    i += 1  # single-line docstring
                else:
                    i += 1
                    while i < len(lines) and '"""' not in lines[i]:
                        i += 1
                    i += 1  # closing """
            # Skip the statement body: blank lines and lines indented past the
            # signature, but STOP at a nested signature (kept) or a dedent.
            removed = False
            while i < len(lines):
                cur = lines[i]
                cur_stripped = cur.strip()
                if cur_stripped == "":
                    i += 1
                    continue
                cur_indent = len(cur) - len(cur.lstrip())
                if cur_indent <= sig_indent:
                    break  # sibling or dedent: this block is done
                if _SIG_START.match(cur.lstrip()):
                    break  # nested signature: let the outer loop keep it
                removed = True
                i += 1
            if removed:
                result.append(" " * body_indent + "...\n")
        else:
            result.append(line)
            i += 1
    return "".join(result)


class CompactCompressionBackend:
    """Structural compression: extracts signatures/docstrings, removes bodies."""

    name = "compact"

    def __init__(self) -> None:
        self._terse = TerseCompressor()

    def compress(self, text: str, protected_spans: list[ProtectedSpan]) -> str:
        if not text:
            return text

        spans = sorted(protected_spans, key=lambda s: s.start) if protected_spans else []

        def _is_protected(start: int, end: int) -> bool:
            for sp in spans:
                if sp.start <= start and end <= sp.end:
                    return True
            return False

        # Process fenced python code blocks
        def _replace_code(m: re.Match) -> str:
            block_start = m.start()
            block_end = m.end()
            if _is_protected(block_start, block_end):
                return m.group(0)
            header, code, footer = m.group(1), m.group(2), m.group(3)
            return header + _compact_python_block(code) + footer

        processed = _FENCED_CODE.sub(_replace_code, text)

        # For non-protected prose regions, apply terse compression
        if spans:
            parts: list[str] = []
            pos = 0
            for span in spans:
                start = max(span.start, pos)
                if start > pos:
                    chunk = processed[pos:start]
                    # Only terse compress if no code fences present
                    if "```" not in chunk:
                        chunk = self._terse.compress(chunk)
                    parts.append(chunk)
                parts.append(text[span.start : span.end])
                pos = span.end
            if pos < len(processed):
                tail = processed[pos:]
                if "```" not in tail:
                    tail = self._terse.compress(tail)
                parts.append(tail)
            return "".join(parts)

        # No protected spans: terse-compress prose sections outside code blocks
        def _compress_prose(m: re.Match) -> str:
            # Between code blocks
            return self._terse.compress(m.group(0))

        # Split on code blocks to compress prose only
        result_parts: list[str] = []
        last = 0
        for m in _FENCED_CODE.finditer(processed):
            prose = processed[last : m.start()]
            result_parts.append(self._terse.compress(prose) if prose else "")
            result_parts.append(m.group(0))
            last = m.end()
        tail = processed[last:]
        result_parts.append(self._terse.compress(tail) if tail else "")
        return "".join(result_parts)
