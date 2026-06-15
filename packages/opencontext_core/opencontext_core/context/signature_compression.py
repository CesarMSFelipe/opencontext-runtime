"""Signature-level compression for source code.

Keeps declarations and signatures (class/def/function headers and the first
docstring line) while eliding bodies. Uses a tree-sitter parse when a grammar
is available for the language and degrades to a regex extractor otherwise.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from opencontext_core.indexing.tree_sitter_parser import LANGUAGE_EXTENSIONS

_DEFINITION_NODE_TYPES = frozenset(
    {
        "function_definition",
        "async_function_definition",
        "class_definition",
        "function_declaration",
        "method_definition",
        "method_declaration",
        "class_declaration",
        "function_item",
        "struct_item",
        "interface_declaration",
        "trait_declaration",
    }
)

_PLACEHOLDER = "..."

_FENCED_CODE = re.compile(r"(```([A-Za-z0-9_+-]*)\n)(.*?)(```)", re.DOTALL)

# Regex fallback: a python-style ``def``/``class`` header line (optionally
# preceded by decorators) ending in a colon.
_PY_HEADER = re.compile(
    r"^([ \t]*)((?:async\s+)?(?:def|class)\s+\w+[^\n]*:)[ \t]*$",
)


class SignatureCompressor:
    """Reduces source code to declarations, signatures, and docstring summaries."""

    def compress(self, text: str, language: str | None = None) -> str:
        """Compress ``text`` to signatures, eliding bodies.

        When ``text`` contains fenced code blocks, only the code inside each
        fence is compressed and surrounding prose is preserved. Otherwise the
        whole input is treated as source in ``language`` (defaulting to Python).
        """

        if not text:
            return text

        if "```" in text:
            return self._compress_with_fences(text)
        return self._compress_source(text, language)

    def _compress_with_fences(self, text: str) -> str:
        def _replace(match: re.Match[str]) -> str:
            header, lang_tag, code, footer = match.groups()
            language = lang_tag or "python"
            return header + self._compress_source(code, language) + footer

        return _FENCED_CODE.sub(_replace, text)

    def _compress_source(self, code: str, language: str | None) -> str:
        if not code.strip():
            return code

        resolved = _normalize_language(language)
        node_text = self._compress_with_tree_sitter(code, resolved)
        if node_text is not None:
            return node_text
        return _compress_with_regex(code)

    def _compress_with_tree_sitter(self, code: str, language: str | None) -> str | None:
        if language is None:
            return None
        parser = _load_parser(language)
        if parser is None:
            return None

        data = code.encode("utf-8")
        tree = parser.parse(data)
        rewritten = _rewrite_node(tree.root_node, data)
        if rewritten is None:
            return None
        # Guard against a degenerate parse that drops everything meaningful.
        if not rewritten.strip():
            return None
        return rewritten


def _normalize_language(language: str | None) -> str | None:
    if language is None:
        return None
    lowered = language.lower()
    if lowered in set(LANGUAGE_EXTENSIONS.values()):
        return lowered
    if lowered in {"py", "python3"}:
        return "python"
    return lowered


@lru_cache(maxsize=16)
def _load_parser(language: str) -> Any | None:
    """Load a tree-sitter parser for ``language`` or return ``None``.

    Mirrors the optional-dependency loading used by the indexing parser so this
    module stays import-safe when tree-sitter or a grammar is unavailable.
    """

    grammar_modules = {
        "python": "tree_sitter_python",
        "javascript": "tree_sitter_javascript",
        "typescript": "tree_sitter_typescript",
        "go": "tree_sitter_go",
        "rust": "tree_sitter_rust",
        "java": "tree_sitter_java",
        "php": "tree_sitter_php",
        "c": "tree_sitter_c",
        "cpp": "tree_sitter_cpp",
        "ruby": "tree_sitter_ruby",
    }
    module_name = grammar_modules.get(language)
    if module_name is None:
        return None

    try:
        from tree_sitter import Language, Parser
    except ImportError:
        return None

    try:
        module = __import__(module_name)
        language_obj = Language(module.language())
    except (ImportError, AttributeError, ValueError):
        return None

    return Parser(language_obj)


def _rewrite_node(node: Any, data: bytes) -> str | None:
    """Rewrite a container node, keeping signatures and eliding bodies.

    Returns the rewritten source for ``node``'s span, or ``None`` when ``node``
    is not a recognised container (so callers keep the original text).
    """

    parts: list[str] = []
    cursor = node.start_byte
    found_definition = False

    for child in node.children:
        body = child.child_by_field_name("body")
        if child.type in _DEFINITION_NODE_TYPES and body is not None:
            found_definition = True
            # Preserve any text (e.g. decorators handled as siblings) between the
            # previous cursor and this definition.
            if child.start_byte > cursor:
                parts.append(data[cursor : child.start_byte].decode("utf-8"))
            parts.append(_rewrite_definition(child, body, data))
            cursor = child.end_byte

    if not found_definition:
        return None

    if cursor < node.end_byte:
        parts.append(data[cursor : node.end_byte].decode("utf-8"))

    return "".join(parts)


def _rewrite_definition(node: Any, body: Any, data: bytes) -> str:
    """Emit a single definition's signature, docstring summary, and nested defs."""

    signature = data[node.start_byte : body.start_byte].decode("utf-8")
    indent = " " * (body.start_point[1])

    pieces: list[str] = [signature.rstrip("\n").rstrip()]

    docstring = _first_docstring_line(body, data)
    if docstring is not None:
        pieces.append(f"\n{indent}{docstring}")

    nested: list[str] = []
    has_other_statements = False
    for child in body.children:
        inner_body = child.child_by_field_name("body")
        if child.type in _DEFINITION_NODE_TYPES and inner_body is not None:
            nested.append(_rewrite_definition(child, inner_body, data))
        elif _is_docstring_statement(child):
            continue
        else:
            has_other_statements = True

    if has_other_statements:
        pieces.append(f"\n{indent}{_PLACEHOLDER}")

    for nested_def in nested:
        pieces.append(f"\n{indent}{nested_def.lstrip()}")

    return "".join(pieces)


def _is_docstring_statement(node: Any) -> bool:
    return (
        node.type == "expression_statement"
        and bool(node.children)
        and node.children[0].type == "string"
    )


def _first_docstring_line(body: Any, data: bytes) -> str | None:
    if not body.children:
        return None
    first = body.children[0]
    if not _is_docstring_statement(first):
        return None
    raw = data[first.start_byte : first.end_byte].decode("utf-8")
    return _docstring_summary(raw)


def _docstring_summary(raw: str) -> str:
    """Return a single-line docstring representation keeping the first line."""

    for quote in ('"""', "'''", '"', "'"):
        if raw.startswith(quote) and raw.endswith(quote) and len(raw) >= 2 * len(quote):
            inner = raw[len(quote) : -len(quote)]
            first_line = inner.strip().splitlines()[0].strip() if inner.strip() else ""
            multiline = "\n" in inner.strip()
            suffix = " ..." if multiline else ""
            return f"{quote}{first_line}{suffix}{quote}"
    return raw.splitlines()[0]


def _compress_with_regex(code: str) -> str:
    """Regex fallback: keep python-style signature lines, drop indented bodies."""

    lines = code.splitlines(keepends=True)
    result: list[str] = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]
        header = _PY_HEADER.match(line.rstrip("\n"))
        if header is None:
            result.append(line)
            index += 1
            continue

        header_indent = len(header.group(1))
        result.append(line if line.endswith("\n") else line + "\n")
        index += 1

        kept_docstring = False
        body_indent: int | None = None
        body_had_statements = False

        while index < total:
            current = lines[index]
            if not current.strip():
                index += 1
                continue
            current_indent = len(current) - len(current.lstrip())
            if current_indent <= header_indent:
                break
            if body_indent is None:
                body_indent = current_indent

            stripped = current.strip()
            if not kept_docstring and (stripped.startswith('"""') or stripped.startswith("'''")):
                quote = stripped[:3]
                first_line = stripped[3:]
                if first_line.endswith(quote) and len(first_line) >= 3:
                    summary = first_line[:-3].strip()
                    result.append(f"{' ' * body_indent}{quote}{summary}{quote}\n")
                    index += 1
                else:
                    summary = first_line.strip()
                    result.append(f"{' ' * body_indent}{quote}{summary} ...{quote}\n")
                    index += 1
                    while index < total and quote not in lines[index]:
                        index += 1
                    if index < total:
                        index += 1
                kept_docstring = True
                continue

            body_had_statements = True
            index += 1

        if body_had_statements:
            placeholder_indent = body_indent if body_indent is not None else header_indent + 4
            result.append(f"{' ' * placeholder_indent}{_PLACEHOLDER}\n")

    return "".join(result)
