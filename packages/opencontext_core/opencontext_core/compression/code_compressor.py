"""CodeCompressor — AST-aware code compression.

Reuses the existing ``TreeSitterParser`` from ``indexing/`` to parse code,
then applies structure-preserving compression:
- Strip docstrings (→ signatures)
- Strip comments
- Shorten local identifiers (non-exported)
- Collapse blank lines

Falls back to regex-based heuristics when tree-sitter is unavailable.
"""

from __future__ import annotations

import re
from typing import Any

from opencontext_core.compat import StrEnum


class CodeCompressionMode(StrEnum):
    """Modes that affect how code may be compacted."""

    PLAN = "plan"
    ARCHITECT = "architect"
    REVIEW = "review"
    IMPLEMENT_PACK = "implement_pack"
    ACT = "act"
    AUDIT = "audit"


# Regex fallback patterns
_DOCSTRING_RE = re.compile(
    r'"""(?:[^"\\]|\\.)*"""'  # double-quoted docstrings
    r"|'''(?:[^'\\]|\\.)*'''"  # single-quoted docstrings
    r'|""".*?"""',  # non-greedy fallback
    re.DOTALL,
)
_COMMENT_RE = re.compile(r"#[^\n]*")
_DECORATOR_RE = re.compile(r"^@\w+(?:\.\w+)*(?:\(.*?\))?\s*$", re.MULTILINE)
_IMPORT_RE = re.compile(r"^(?:from|import)\s", re.MULTILINE)
_FUNC_DEF_RE = re.compile(r"^(?:async\s+)?def\s+(\w+)\s*\(", re.MULTILINE)
_CLASS_DEF_RE = re.compile(r"^class\s+(\w+)", re.MULTILINE)
_EMPTY_LINE_RE = re.compile(r"\n\s*\n")
_MULTI_SPACE_RE = re.compile(r"  +")


def _python_comment_columns(content: str) -> dict[int, int] | None:
    """Map 1-based line -> column where a real ``#`` comment starts.

    Uses ``tokenize`` so a ``#`` inside a string literal is never mistaken for a
    comment. Returns ``None`` when the source cannot be tokenized (caller then
    falls back to naive splitting, acceptable on already-broken code).
    """
    import io
    import tokenize

    cols: dict[int, int] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(content).readline):
            if tok.type == tokenize.COMMENT:
                row, col = tok.start
                if row not in cols or col < cols[row]:
                    cols[row] = col
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        return None
    return cols


def _strip_inline_line_comment(line: str, marker: str) -> str | None:
    """Return the code before an *unquoted* ``marker`` (e.g. ``//``), else ``None``.

    Tracks ``'`` ``"`` and `` ` `` string state with backslash escapes so a marker
    inside a string (``"http://x"``) is not treated as a comment.
    """
    quote: str | None = None
    i = 0
    n = len(line)
    mlen = len(marker)
    while i < n:
        ch = line[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
            i += 1
            continue
        if line[i : i + mlen] == marker:
            return line[:i]
        i += 1
    return None


def _ast_strip_python_docstrings(content: str) -> str | None:
    """Blank only real docstrings (first string stmt of module/class/def).

    Returns ``None`` when the source is not parseable Python, so callers keep the
    blunt regex strictly for unparseable input — triple-quoted *data* strings
    (SQL, templates) survive on the valid-Python path.
    """
    import ast

    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return None
    lines = content.split("\n")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            start = first.lineno
            end = getattr(first, "end_lineno", start) or start
            for i in range(start - 1, min(end, len(lines))):
                lines[i] = ""
    return "\n".join(lines)


class CodeCompressor:
    """Compress source code while preserving semantic structure.

    Uses tree-sitter when available; degrades to regex heuristics.
    """

    def __init__(self, *, tree_sitter_parser: Any | None = None) -> None:
        self._ts_parser = tree_sitter_parser
        self._ts_available = False
        self._init_tree_sitter()

    def _init_tree_sitter(self) -> None:
        if self._ts_parser is not None:
            self._ts_available = getattr(self._ts_parser, "is_available", lambda: False)()
            return
        try:
            from opencontext_core.indexing.tree_sitter_parser import TreeSitterParser

            parser = TreeSitterParser()
            self._ts_available = parser.is_available()
            if self._ts_available:
                self._ts_parser = parser
        except ImportError:
            self._ts_available = False

    def compress(
        self,
        content: str,
        *,
        language: str | None = None,
        mode: CodeCompressionMode = CodeCompressionMode.REVIEW,
        strip_docstrings: bool = True,
        strip_comments: bool = True,
        shorten_locals: bool = True,
        preserve_exports: bool = True,
    ) -> str:
        """Compress source code.

        Args:
            content: Raw source code.
            language: Language hint (e.g. 'python', 'javascript').
            mode: Compression granularity.
            strip_docstrings: Replace docstrings with signatures.
            strip_comments: Remove comments.
            shorten_locals: Shorten non-exported identifiers.
            preserve_exports: Never shorten public/exported symbols.

        Returns:
            Compressed source code.
        """
        if not content.strip():
            return content

        # Mode overrides individual flags
        if mode == CodeCompressionMode.PLAN:
            return self._compress_to_signatures(content, language=language)
        if mode == CodeCompressionMode.ACT:
            return content
        if mode == CodeCompressionMode.IMPLEMENT_PACK:
            strip_docstrings = False
            strip_comments = True
            shorten_locals = False

        result = content

        if strip_docstrings:
            result = self._strip_docstrings(result, language=language)

        if strip_comments:
            result = self._strip_comments(result, language=language)

        if mode == CodeCompressionMode.ARCHITECT:
            result = self._compress_to_type_stubs(result, language=language)

        if shorten_locals and mode in (CodeCompressionMode.REVIEW,):
            result = self._shorten_locals(
                result, language=language, preserve_exports=preserve_exports
            )

        # Collapse blank lines (preserve at most 1)
        result = _EMPTY_LINE_RE.sub("\n", result)
        result = _MULTI_SPACE_RE.sub(" ", result)

        return result.strip()

    def _strip_docstrings(self, content: str, *, language: str | None = None) -> str:
        """Remove docstrings, leaving just the function/class signature."""
        if self._ts_available and language:
            return self._ts_strip_docstrings(content, language)
        ast_stripped = _ast_strip_python_docstrings(content)
        if ast_stripped is not None:
            return ast_stripped
        return _DOCSTRING_RE.sub("", content)

    def _ts_strip_docstrings(self, content: str, language: str) -> str:
        """Tree-sitter based docstring removal."""
        if self._ts_parser is None:
            return content
        try:
            placeholder = "/tmp/placeholder." + _ext_for_lang(language)
            result = self._ts_parser.parse_file(placeholder, content)
            symbols = result.symbols if hasattr(result, "symbols") else []
            # Replace docstrings with signature lines
            lines = content.splitlines()
            for sym in symbols:
                if sym.docstring and sym.line > 0:
                    sig = sym.signature or ""
                    # Replace docstring lines with the signature
                    docstring_start = sym.line  # line after signature
                    docstring_end = sym.end_line
                    if docstring_start < len(lines) and docstring_end <= len(lines):
                        for i in range(docstring_start, docstring_end):
                            lines[i] = ""
                        if sig:
                            lines[docstring_start - 1] = sig
            return "\n".join(line for line in lines if line.strip())
        except Exception:
            ast_stripped = _ast_strip_python_docstrings(content)
            if ast_stripped is not None:
                return ast_stripped
            return _DOCSTRING_RE.sub("", content)

    def _strip_comments(self, content: str, *, language: str | None = None) -> str:
        """Remove comments but keep shebangs and pragmas."""
        _PRAGMAS = ("noqa", "pragma:", "type: ignore", "# coding:")
        if language == "python":
            comment_cols = _python_comment_columns(content)
            if comment_cols is None:
                return self._strip_comments_python_naive(content, _PRAGMAS)
            lines = content.splitlines()
            cleaned = []
            for idx, line in enumerate(lines, start=1):
                if line.lstrip().startswith("#!"):
                    cleaned.append(line)
                    continue
                col = comment_cols.get(idx)
                if col is None:
                    cleaned.append(line)  # no real comment (a '#' here is in a string)
                    continue
                comment_text = line[col:]
                if any(marker in comment_text for marker in _PRAGMAS):
                    cleaned.append(line)  # preserve pragma/coding/noqa line as-is
                    continue
                code_part = line[:col].rstrip()
                if code_part:
                    cleaned.append(code_part)
                # else: comment-only line -> drop
            return "\n".join(cleaned)
        # Generic: remove comment lines, keep inline comments with code. The // is
        # only a comment when it is not inside a string literal.
        lines = content.splitlines()
        result: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                result.append(line)
            elif stripped.startswith("//") or stripped.startswith("/*"):
                continue
            else:
                code = _strip_inline_line_comment(line, "//")
                if code is None:
                    result.append(line)  # no real // comment
                elif code.rstrip():
                    result.append(code.rstrip())
        return "\n".join(result)

    @staticmethod
    def _strip_comments_python_naive(content: str, pragmas: tuple[str, ...]) -> str:
        """Naive line-based comment strip — only for source ``tokenize`` rejects."""
        cleaned: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#!") or any(marker in stripped for marker in pragmas):
                cleaned.append(line)
                continue
            if _COMMENT_RE.search(stripped) and not stripped.startswith("#"):
                code_part = _COMMENT_RE.split(line)[0].rstrip()
                if code_part:
                    cleaned.append(code_part)
                continue
            if stripped.startswith("#"):
                continue
            cleaned.append(line)
        return "\n".join(cleaned)

    def _compress_to_signatures(self, content: str, *, language: str | None = None) -> str:
        """Reduce to just function/class signatures and imports."""
        if language == "python":
            lines = content.splitlines()
            kept: list[str] = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                if _IMPORT_RE.match(stripped):
                    kept.append(line)
                elif _FUNC_DEF_RE.match(stripped) or _CLASS_DEF_RE.match(stripped):
                    # Add the decorator line before, if any
                    if kept and kept[-1].strip().startswith("@"):
                        kept.append(line)
                    else:
                        kept.append(line)
                    # Add the def/class line (may have body on same line)
                    if stripped.endswith(":") or stripped.endswith("("):
                        kept.append("    ...  # snipped")
                elif stripped.startswith("@"):
                    kept.append(stripped)
            return "\n".join(kept)
        return content

    def _compress_to_type_stubs(self, content: str, *, language: str | None = None) -> str:
        """Keep signatures + type annotations, drop bodies."""
        if language == "python":
            lines = content.splitlines()
            kept: list[str] = []
            indent_level = 0
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                # Track indentation to detect body lines
                curr_indent = len(line) - len(line.lstrip())
                if curr_indent <= indent_level and indent_level > 0:
                    pass  # back to parent level
                if stripped.endswith(":") and not stripped.startswith("#"):
                    kept.append(line)
                    indent_level = curr_indent + 4
                    if not stripped.startswith(("def ", "class ", "async ")):
                        pass  # control flow — keep
                elif curr_indent < indent_level or indent_level == 0:
                    kept.append(line)
            return "\n".join(kept)
        return content

    def _shorten_locals(
        self, content: str, *, language: str | None = None, preserve_exports: bool = True
    ) -> str:
        """Shorten non-exported local identifiers to 1-2 chars.

        Only affects Python. Uses a conservative heuristic: any name that
        appears in a function body (local) and is NOT in imports/globals/params.
        """
        if language != "python":
            return content

        lines = content.splitlines()
        # Collect exported names (never shorten)
        exported: set[str] = set()
        if preserve_exports:
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("def ") or stripped.startswith("class "):
                    name = stripped.split()[1].split("(")[0].split(":")[0]
                    if not name.startswith("_"):
                        exported.add(name)
                if "= __all__" in stripped or "__all__ =" in stripped:
                    pass  # would need AST

        # Build replacement map for local vars in function bodies
        import ast as _py_ast

        replacements: dict[str, str] = {}
        try:
            tree = _py_ast.parse(content)
            for node in _py_ast.walk(tree):
                if isinstance(node, _py_ast.FunctionDef):
                    # Parameters
                    for arg in node.args.args:
                        name = arg.arg
                        if name not in exported and len(name) > 2 and not name.startswith("_"):
                            replacements[name] = _short_name(name, replacements)
                    # Body-level names
                    for child in _py_ast.walk(node):
                        if isinstance(child, _py_ast.Name):
                            name = child.id
                            if (
                                not isinstance(child.ctx, _py_ast.Load)
                                and name not in exported
                                and len(name) > 2
                                and not name.startswith("_")
                                and _is_local_context(child, node)
                            ):
                                replacements[name] = replacements.get(
                                    name, _short_name(name, replacements)
                                )
        except SyntaxError:
            pass

        if not replacements:
            return content

        # Apply replacements via tokenize so ONLY NAME tokens are renamed — string
        # and comment contents are never touched — and position-based edits preserve
        # the original spacing (the old split-and-rejoin corrupted identifiers inside
        # strings and padded every bracket/operator with spaces).
        import io
        import tokenize as _tokenize

        try:
            toks = list(_tokenize.generate_tokens(io.StringIO(content).readline))
        except (_tokenize.TokenError, IndentationError, SyntaxError):
            return content

        edits_by_row: dict[int, list[tuple[int, int, str]]] = {}
        for tok in toks:
            if tok.type == _tokenize.NAME and tok.string in replacements:
                edits_by_row.setdefault(tok.start[0], []).append(
                    (tok.start[1], tok.end[1], replacements[tok.string])
                )

        out_lines = content.split("\n")
        for row, edits in edits_by_row.items():
            if not 1 <= row <= len(out_lines):
                continue
            line = out_lines[row - 1]
            for start_col, end_col, new in sorted(edits, reverse=True):  # right-to-left
                line = line[:start_col] + new + line[end_col:]
            out_lines[row - 1] = line

        return "\n".join(out_lines)


def _short_name(name: str, existing: dict[str, str]) -> str:
    """Generate a short unique replacement for a name."""
    # Use first letter + optional suffix
    base = name[0]
    if base not in {v[0] for v in existing.values()}:
        return base
    suffix = 1
    while True:
        candidate = f"{base}{suffix}"
        if candidate not in existing.values():
            return candidate
        suffix += 1


def _is_local_context(node: Any, function_def: Any) -> bool:
    """Check if a Name node is a local variable within a function."""
    parent = getattr(node, "parent", None)
    if parent is None:
        return True  # conservative
    # Skip imports, function names, class names
    if isinstance(parent, (type(None),)):
        return False
    return True


def _ext_for_lang(language: str) -> str:
    _MAP = {
        "python": ".py",
        "javascript": ".js",
        "typescript": ".ts",
        "go": ".go",
        "rust": ".rs",
        "java": ".java",
        "c": ".c",
        "cpp": ".cpp",
        "ruby": ".rb",
        "php": ".php",
        "swift": ".swift",
        "kotlin": ".kt",
    }
    return _MAP.get(language, ".txt")


__all__ = ["CodeCompressionMode", "CodeCompressor"]
