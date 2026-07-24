"""Tree-sitter based symbol extraction and AST parsing.

Wraps tree-sitter Python bindings for multi-language symbol extraction.
Gracefully degrades to regex-based extraction if tree-sitter is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cs": "csharp",
    ".php": "php",
    ".rb": "ruby",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".sc": "scala",
    ".dart": "dart",
    ".svelte": "svelte",
    ".vue": "vue",
    ".liquid": "liquid",
    ".pas": "pascal",
    ".dpr": "pascal",
    ".dpk": "pascal",
    ".lpr": "pascal",
}

# Tree-sitter node types that add a decision path for cyclomatic complexity.
# Python is the MVP target; other languages are mapped where the grammar node
# names line up. Each function gets a base of 1 (the single entry path) plus one
# per decision node found in its body.
_PYTHON_DECISION_TYPES: frozenset[str] = frozenset(
    {
        "if_statement",
        "elif_clause",
        "for_statement",
        "while_statement",
        "except_clause",
        "boolean_operator",  # 'and' / 'or'
        "conditional_expression",  # x if c else y
        "assert_statement",
        "with_statement",
    }
)
_DEFAULT_DECISION_TYPES: frozenset[str] = _PYTHON_DECISION_TYPES
_COMPLEXITY_DECISION_TYPES: dict[str, frozenset[str]] = {
    "python": _PYTHON_DECISION_TYPES,
}

# Node types that introduce a new function/method scope (a complexity row).
_PYTHON_FUNCTION_TYPES: frozenset[str] = frozenset(
    {"function_definition", "async_function_definition"}
)
_DEFAULT_FUNCTION_TYPES: frozenset[str] = _PYTHON_FUNCTION_TYPES
_FUNCTION_NODE_TYPES: dict[str, frozenset[str]] = {
    "python": _PYTHON_FUNCTION_TYPES,
}

# Node types that open a new CODE block-nesting level (for ``max_nesting_depth``).
# This is CODE nesting (if/for/while/with/try/except branches), NOT directory
# nesting — the two are deliberately distinct signals. Same dict-keyed-by-language
# + ``_DEFAULT_*`` fallback pattern as the complexity/function sets above.
_PYTHON_NESTING_TYPES: frozenset[str] = frozenset(
    {
        "if_statement",
        "for_statement",
        "while_statement",
        "with_statement",
        "try_statement",
        "elif_clause",
        "else_clause",
        "except_clause",
    }
)
_DEFAULT_NESTING_TYPES: frozenset[str] = _PYTHON_NESTING_TYPES
_NESTING_TYPES: dict[str, frozenset[str]] = {
    "python": _PYTHON_NESTING_TYPES,
}

# Declaration node types the GENERIC extractor turns into symbols, per language.
# Used for grammars that load but have no dedicated ``_extract_*`` (c, cpp,
# ruby, csharp, and future kotlin/swift). Each set was derived empirically from
# the installed grammar's parse tree, not guessed — the node names differ per
# language (C/C++ use ``*_specifier``/``function_definition`` with the name
# buried in a ``declarator`` subtree; C# uses ``*_declaration``; Ruby uses bare
# ``class``/``module``/``method``). Symbols are the priority; edges are optional
# for these languages and the generic path emits none.
_GENERIC_SYMBOL_NODE_TYPES: dict[str, frozenset[str]] = {
    "c": frozenset(
        {
            "function_definition",
            "struct_specifier",
            "enum_specifier",
            "union_specifier",
            "type_definition",
        }
    ),
    "cpp": frozenset(
        {
            "function_definition",
            "class_specifier",
            "struct_specifier",
            "enum_specifier",
            "union_specifier",
            "namespace_definition",
        }
    ),
    "ruby": frozenset({"class", "module", "method", "singleton_method"}),
    "csharp": frozenset(
        {
            "class_declaration",
            "struct_declaration",
            "interface_declaration",
            "enum_declaration",
            "record_declaration",
            "method_declaration",
            "constructor_declaration",
            "namespace_declaration",
        }
    ),
    # Best-effort for grammars that may be added later; safe supersets that
    # match the common tree-sitter naming. Absent a loaded grammar these are
    # simply never consulted.
    "kotlin": frozenset({"class_declaration", "object_declaration", "function_declaration"}),
    "swift": frozenset(
        {
            "class_declaration",
            "protocol_declaration",
            "function_declaration",
            "init_declaration",
        }
    ),
}

# Generic node type -> emitted symbol ``kind``. Anything not listed falls back
# to a coarse class/function guess in :meth:`TreeSitterParser._extract_generic`.
_GENERIC_KIND_BY_TYPE: dict[str, str] = {
    "function_definition": "function",
    "function_declaration": "function",
    "method_declaration": "method",
    "constructor_declaration": "method",
    "method": "method",
    "singleton_method": "method",
    "init_declaration": "method",
    "struct_specifier": "struct",
    "struct_declaration": "struct",
    "class_specifier": "class",
    "class_declaration": "class",
    "object_declaration": "class",
    "record_declaration": "class",
    "interface_declaration": "interface",
    "protocol_declaration": "interface",
    "enum_specifier": "enum",
    "enum_declaration": "enum",
    "union_specifier": "struct",
    "type_definition": "type",
    "namespace_definition": "namespace",
    "namespace_declaration": "namespace",
    "module": "module",
    "class": "class",
}


@dataclass
class ParsedSymbol:
    """A symbol extracted from source code."""

    name: str
    kind: str
    line: int
    column: int
    end_line: int
    container: str | None
    docstring: str | None
    signature: str | None
    is_exported: bool = False
    content_snippet: str | None = None


@dataclass
class ParsedEdge:
    """A relationship edge extracted from source code.

    ``target_name`` is the full call target text (e.g. ``self._step``, ``b.helper``,
    ``foo``). ``attr`` and ``receiver`` decompose a dotted target so the resolver can
    bind method/attribute calls: for ``b.helper`` -> attr=``helper`` receiver=``b``;
    for a bare ``foo`` -> attr=``foo`` receiver=``None``.
    """

    source_name: str
    target_name: str
    kind: str
    call_site_line: int | None
    attr: str | None = None
    receiver: str | None = None


def _module_binding_names(left: Any) -> list[str]:
    """Identifier name(s) bound by a module-level assignment target.

    Handles a single name (``X = ...``) and tuple/list unpacking
    (``A, B = ...``). Subscript/attribute targets (``d[k] = ...``) bind no new
    module symbol and are skipped.
    """

    if left.type == "identifier":
        return [str(left.text.decode("utf-8"))]
    if left.type in ("pattern_list", "tuple_pattern", "tuple", "expression_list", "list_pattern"):
        return [
            str(child.text.decode("utf-8")) for child in left.children if child.type == "identifier"
        ]
    return []


@dataclass
class ParseFileResult:
    """Outcome of parsing a single file, including parse-mode provenance."""

    symbols: list[ParsedSymbol]
    edges: list[ParsedEdge]
    mode: str  # "tree_sitter" | "regex" | "none"
    language: str | None

    @property
    def degraded(self) -> bool:
        """True when the file did not get a precise tree-sitter parse."""
        return self.mode != "tree_sitter"


class TreeSitterParser:
    """Parser using tree-sitter for AST-level symbol extraction.

    Falls back to regex-based extraction if tree-sitter is not installed
    or the language grammar is unavailable.
    """

    def __init__(self) -> None:
        self._available = False
        self._languages: dict[str, Any] = {}
        self._fallback_parser: Any | None = None
        self._init_tree_sitter()

    def _init_tree_sitter(self) -> None:
        """Attempt to import tree-sitter and load language grammars."""

        try:
            from tree_sitter import Parser

            self._available = True
            self._parser_class = Parser

            # Try to load common language grammars
            self._load_language("python", "tree_sitter_python")
            self._load_language("javascript", "tree_sitter_javascript")
            # tree_sitter_typescript exposes language_typescript(), not language()
            self._load_language(
                "typescript", "tree_sitter_typescript", fn_name="language_typescript"
            )
            self._load_language("go", "tree_sitter_go")
            self._load_language("rust", "tree_sitter_rust")
            self._load_language("java", "tree_sitter_java")
            # tree_sitter_php exposes language_php() (and language_php_only()),
            # NOT language() — the combined-grammar wheel keys the frontend by
            # variant, so the default fn_name silently fails to load PHP.
            self._load_language("php", "tree_sitter_php", fn_name="language_php")
            self._load_language("c", "tree_sitter_c")
            self._load_language("cpp", "tree_sitter_cpp")
            self._load_language("ruby", "tree_sitter_ruby")
            # tree_sitter_c_sharp ships under the module name tree_sitter_c_sharp
            # (dist "tree-sitter-c-sharp"); LANGUAGE_EXTENSIONS maps .cs -> "csharp".
            self._load_language("csharp", "tree_sitter_c_sharp")
            self._load_language("swift", "tree_sitter_swift")
            self._load_language("kotlin", "tree_sitter_kotlin")

        except ImportError:
            self._available = False

        # Fallback to existing regex extractor
        if not self._available:
            from opencontext_core.indexing.symbol_extractor import SymbolExtractor

            self._fallback_parser = SymbolExtractor()

    def _load_language(self, name: str, module_name: str, fn_name: str = "language") -> bool:
        """Attempt to load a tree-sitter language grammar.

        ``fn_name`` is the callable on the grammar package that returns the
        PyCapsule.  Most packages expose ``language()``; ``tree_sitter_typescript``
        exposes ``language_typescript()`` and ``language_tsx()`` instead.
        """

        if not self._available:
            return False

        try:
            module = __import__(module_name)
            language_fn = getattr(module, fn_name)
            language_capsule = language_fn()
            # Wrap PyCapsule in tree_sitter.Language
            from tree_sitter import Language as TSLanguage

            language = TSLanguage(language_capsule)
            self._languages[name] = language
            return True
        except (ImportError, AttributeError):
            return False

    def is_available(self) -> bool:
        """Whether tree-sitter is installed and available."""

        return self._available

    def detect_language(self, file_path: str) -> str | None:
        """Detect language from file extension."""

        suffix = Path(file_path).suffix.lower()
        return LANGUAGE_EXTENSIONS.get(suffix)

    def parse_file(
        self, file_path: str, content: str
    ) -> tuple[list[ParsedSymbol], list[ParsedEdge]]:
        """Parse a file and extract symbols and edges.

        Args:
            file_path: Relative path to the file.
            content: File content.

        Returns:
            Tuple of (symbols, edges).
        """

        result = self.parse_file_status(file_path, content)
        return result.symbols, result.edges

    def parse_file_status(self, file_path: str, content: str) -> ParseFileResult:
        """Parse a file, returning symbols, edges, and the parse-mode provenance.

        Distinguishes a precise tree-sitter parse from a degraded regex fallback so
        callers can surface a per-file parse status instead of silently presenting
        regex output (which emits zero edges) as a fully-resolved index.
        """

        language = self.detect_language(file_path)
        if language is None:
            return ParseFileResult(symbols=[], edges=[], mode="none", language=None)

        # Use tree-sitter if available and language grammar loaded
        if self._available and language in self._languages:
            symbols, edges = self._parse_with_tree_sitter(file_path, content, language)
            return ParseFileResult(
                symbols=symbols, edges=edges, mode="tree_sitter", language=language
            )

        # No loaded grammar -> degraded regex fallback (symbols only, zero edges).
        symbols, edges = self._parse_with_fallback(file_path, content, language)
        return ParseFileResult(symbols=symbols, edges=edges, mode="regex", language=language)

    def cyclomatic_complexity(self, content: str, language: str) -> list[tuple[str, int, int]]:
        """Return ``(symbol_name, complexity, start_line)`` per function/method.

        Reuses the same tree-sitter parse path as symbol extraction: parses
        ``content`` with the loaded grammar, then for each function/method subtree
        walks its body counting decision points and adds a base of 1 (the single
        entry path). The Python decision set is enumerated first
        (``if_statement``, ``elif_clause``, ``for_statement``, ``while_statement``,
        ``except_clause``, ``boolean_operator`` for ``and``/``or``,
        ``conditional_expression``); other languages contribute their analogous
        node types where the grammar names match.

        Degrades honestly: returns ``[]`` when tree-sitter is unavailable or the
        language grammar is not loaded (the caller records this as a *skipped*
        rule, never a clean pass). Deterministic for identical input.
        """
        if not self.is_available() or language not in self._languages:
            return []

        try:
            parser = self._parser_class(self._languages[language])
            tree = parser.parse(bytes(content, "utf-8"))
        except Exception:
            return []
        root = tree.root_node

        decision_types = _COMPLEXITY_DECISION_TYPES.get(language, _DEFAULT_DECISION_TYPES)
        func_types = _FUNCTION_NODE_TYPES.get(language, _DEFAULT_FUNCTION_TYPES)

        results: list[tuple[str, int, int]] = []

        def measure(node: Any) -> int:
            """Cyclomatic complexity of one function subtree (base 1 + decisions)."""
            count = 1
            stack = list(node.children)
            while stack:
                child = stack.pop()
                # Do not descend into a *nested* function: its complexity is
                # reported on its own row, not folded into the enclosing one.
                if child is not node and child.type in func_types:
                    continue
                if child.type in decision_types:
                    count += 1
                stack.extend(child.children)
            return count

        def walk(node: Any) -> None:
            if node.type in func_types:
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    name = name_node.text.decode("utf-8", errors="replace")
                    results.append((name, measure(node), node.start_point[0] + 1))
            for child in node.children:
                walk(child)

        walk(root)
        # Stable order: by start line, then name (handles same-line edge cases).
        results.sort(key=lambda r: (r[2], r[0]))
        return results

    def function_blocks(self, content: str, language: str) -> list[tuple[str, int, int, str]]:
        """Return ``(symbol_name, start_line, end_line, normalized_body)`` per function.

        Reuses the exact parse path + degrade-honestly guard + determinism of
        :meth:`cyclomatic_complexity`: same availability/grammar gate, same
        ``func_types`` walk, same ``child_by_field_name('name')`` guard and
        ``start_point[0] + 1`` line convention. ``normalized_body`` is the
        function subtree's source text run through a deterministic normalizer
        (runs of ASCII whitespace collapsed to a single space, then stripped) so
        cosmetic indentation / blank-line / formatting differences do not hide a
        clone. Results are sorted by ``(start_line, name)``.

        Degrades honestly: ``[]`` when tree-sitter is unavailable or the grammar
        is not loaded (the caller records a *skipped* reason, never a clean pass).
        """
        if not self.is_available() or language not in self._languages:
            return []

        try:
            parser = self._parser_class(self._languages[language])
            tree = parser.parse(bytes(content, "utf-8"))
        except Exception:
            return []
        root = tree.root_node

        func_types = _FUNCTION_NODE_TYPES.get(language, _DEFAULT_FUNCTION_TYPES)

        results: list[tuple[str, int, int, str]] = []

        def walk(node: Any) -> None:
            if node.type in func_types:
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    name = name_node.text.decode("utf-8", errors="replace")
                    raw = node.text.decode("utf-8", errors="replace")
                    # Deterministic normalizer: collapse ASCII-whitespace runs to a
                    # single space and strip, so format-only diffs do not mask a clone.
                    normalized = " ".join(raw.split())
                    results.append(
                        (name, node.start_point[0] + 1, node.end_point[0] + 1, normalized)
                    )
            for child in node.children:
                walk(child)

        walk(root)
        results.sort(key=lambda r: (r[1], r[0]))
        return results

    def max_nesting_depth(self, content: str, language: str) -> list[tuple[str, int, int]]:
        """Return ``(symbol_name, max_block_depth, start_line)`` per function/method.

        Reuses the same parse path + ``func_types`` discovery as
        :meth:`cyclomatic_complexity`. For each function subtree it runs a
        stack-walk tracking the running CODE block-nesting depth: depth is
        incremented when entering a node whose type is in :data:`_NESTING_TYPES`,
        and the maximum is recorded. Descent STOPS at a nested function (its
        nesting is reported on its own row), mirroring the nested-function skip in
        :meth:`cyclomatic_complexity`. Results are sorted by ``(start_line, name)``.

        Degrades honestly: ``[]`` when tree-sitter is unavailable or the grammar
        is not loaded.
        """
        if not self.is_available() or language not in self._languages:
            return []

        try:
            parser = self._parser_class(self._languages[language])
            tree = parser.parse(bytes(content, "utf-8"))
        except Exception:
            return []
        root = tree.root_node

        func_types = _FUNCTION_NODE_TYPES.get(language, _DEFAULT_FUNCTION_TYPES)
        nesting_types = _NESTING_TYPES.get(language, _DEFAULT_NESTING_TYPES)

        results: list[tuple[str, int, int]] = []

        def measure(node: Any) -> int:
            """Deepest CODE block-nesting within one function subtree."""
            max_depth = 0
            # (child_node, depth_at_this_node) — start each direct child at the
            # base depth (the function's own body is level 0).
            stack: list[tuple[Any, int]] = [(child, 0) for child in node.children]
            while stack:
                child, depth = stack.pop()
                # Do not descend into a *nested* function: its nesting is reported
                # on its own row, not folded into the enclosing one.
                if child is not node and child.type in func_types:
                    continue
                child_depth = depth
                if child.type in nesting_types:
                    child_depth = depth + 1
                    if child_depth > max_depth:
                        max_depth = child_depth
                stack.extend((grandchild, child_depth) for grandchild in child.children)
            return max_depth

        def walk(node: Any) -> None:
            if node.type in func_types:
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    name = name_node.text.decode("utf-8", errors="replace")
                    results.append((name, measure(node), node.start_point[0] + 1))
            for child in node.children:
                walk(child)

        walk(root)
        results.sort(key=lambda r: (r[2], r[0]))
        return results

    def _parse_with_tree_sitter(
        self, file_path: str, content: str, language: str
    ) -> tuple[list[ParsedSymbol], list[ParsedEdge]]:
        """Parse using tree-sitter AST."""

        parser = self._parser_class(self._languages[language])
        tree = parser.parse(bytes(content, "utf-8"))
        root = tree.root_node

        symbols: list[ParsedSymbol] = []
        edges: list[ParsedEdge] = []

        # Language-specific extraction
        if language == "python":
            symbols, edges = self._extract_python(file_path, content, root)
        elif language in ("javascript", "typescript"):
            symbols, edges = self._extract_js_ts(file_path, content, root)
        elif language == "go":
            symbols, edges = self._extract_go(file_path, content, root)
        elif language == "rust":
            symbols, edges = self._extract_rust(file_path, content, root)
        elif language == "java":
            symbols, edges = self._extract_java(file_path, content, root)
        elif language == "php":
            symbols, edges = self._extract_php(file_path, content, root)
        else:
            # Any loaded grammar WITHOUT a dedicated extractor (c, cpp, ruby,
            # csharp, kotlin, swift, …) falls through here. Before this fallback
            # existed the parse returned empty symbols/edges — a loaded grammar
            # that indexed nothing. The generic extractor pulls declaration-level
            # symbols so these languages are searchable in the KG.
            symbols, edges = self._extract_generic(file_path, content, root, language)

        return symbols, edges

    def _parse_with_fallback(
        self, file_path: str, content: str, language: str
    ) -> tuple[list[ParsedSymbol], list[ParsedEdge]]:
        """Fallback to regex-based extraction."""

        if self._fallback_parser is None:
            return [], []

        from opencontext_core.indexing.symbol_extractor import ExtractableFile

        file = ExtractableFile(
            relative_path=file_path,
            language=language,
            content=content,
        )
        extracted = self._fallback_parser.extract(file)

        symbols = [
            ParsedSymbol(
                name=s.name,
                kind=s.kind,
                line=s.line,
                column=0,
                end_line=s.line,
                container=s.container,
                docstring=None,
                signature=None,
                is_exported=True,
            )
            for s in extracted
        ]

        return symbols, []

    def _extract_python(
        self, file_path: str, content: str, root: Any
    ) -> tuple[list[ParsedSymbol], list[ParsedEdge]]:
        """Extract symbols from Python AST."""

        symbols: list[ParsedSymbol] = []
        edges: list[ParsedEdge] = []
        current_class: str | None = None

        def walk(node: Any, depth: int = 0) -> None:
            nonlocal current_class

            if node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    current_class = name_node.text.decode("utf-8")
                    symbols.append(
                        ParsedSymbol(
                            name=current_class,
                            kind="class",
                            line=node.start_point[0] + 1,
                            column=node.start_point[1],
                            end_line=node.end_point[0] + 1,
                            container=None,
                            docstring=self._extract_docstring(node, content),
                            signature=None,
                            is_exported=True,
                            content_snippet=self._snippet(node),
                        )
                    )

            elif node.type in ("function_definition", "async_function_definition"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    func_name = name_node.text.decode("utf-8")
                    container = current_class if current_class else None
                    kind = "method" if current_class else "function"

                    symbols.append(
                        ParsedSymbol(
                            name=func_name,
                            kind=kind,
                            line=node.start_point[0] + 1,
                            column=node.start_point[1],
                            end_line=node.end_point[0] + 1,
                            container=container,
                            docstring=self._extract_docstring(node, content),
                            signature=self._extract_signature(node, content),
                            is_exported=True,
                            content_snippet=self._snippet(node),
                        )
                    )

                    # Extract call edges
                    edges.extend(self._extract_calls(node, func_name, file_path))

            # Recurse
            for child in node.children:
                walk(child, depth + 1)

            if node.type == "class_definition":
                current_class = None

        walk(root)

        # Module-level bindings (PERSONAS = {...}, DEFAULT_IGNORE = [...], app = ...).
        # These define registries/constants/config as DATA, not def/class, so a
        # symbol search that only knows functions and classes is blind to the file
        # that "defines" them. Index the name(s) plus a one-line RHS snippet so both
        # the identifier and the assigned content are searchable. Module level only
        # (direct children of the module node) — locals inside functions stay out,
        # so the index does not explode.
        for child in root.children:
            if child.type != "expression_statement":
                continue
            for sub in child.children:
                if sub.type != "assignment":
                    continue
                left = sub.child_by_field_name("left")
                if left is None:
                    continue
                names = _module_binding_names(left)
                if not names:
                    continue
                snippet = " ".join(str(sub.text.decode("utf-8")).split())[:200]
                for name in names:
                    symbols.append(
                        ParsedSymbol(
                            name=name,
                            kind="constant" if name.isupper() else "variable",
                            line=sub.start_point[0] + 1,
                            column=sub.start_point[1],
                            end_line=sub.end_point[0] + 1,
                            container=None,
                            docstring=None,
                            signature=snippet,
                            is_exported=not name.startswith("_"),
                            content_snippet=snippet,
                        )
                    )

        return symbols, edges

    def _extract_js_ts(
        self, file_path: str, content: str, root: Any
    ) -> tuple[list[ParsedSymbol], list[ParsedEdge]]:
        """Extract symbols from JavaScript/TypeScript AST."""

        symbols: list[ParsedSymbol] = []
        edges: list[ParsedEdge] = []

        def walk(node: Any) -> None:
            if node.type in ("function_declaration", "method_definition"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    func_name = name_node.text.decode("utf-8")
                    kind = "method" if node.type == "method_definition" else "function"
                    symbols.append(
                        ParsedSymbol(
                            name=func_name,
                            kind=kind,
                            line=node.start_point[0] + 1,
                            column=node.start_point[1],
                            end_line=node.end_point[0] + 1,
                            container=None,
                            docstring=None,
                            signature=None,
                            is_exported=True,
                            content_snippet=self._snippet(node),
                        )
                    )
                    edges.extend(self._extract_calls(node, func_name, file_path))

            elif node.type == "class_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    class_name = name_node.text.decode("utf-8")
                    symbols.append(
                        ParsedSymbol(
                            name=class_name,
                            kind="class",
                            line=node.start_point[0] + 1,
                            column=node.start_point[1],
                            end_line=node.end_point[0] + 1,
                            container=None,
                            docstring=None,
                            signature=None,
                            is_exported=True,
                            content_snippet=self._snippet(node),
                        )
                    )

            for child in node.children:
                walk(child)

        walk(root)
        return symbols, edges

    def _extract_go(
        self, file_path: str, content: str, root: Any
    ) -> tuple[list[ParsedSymbol], list[ParsedEdge]]:
        """Extract symbols from Go AST."""

        symbols: list[ParsedSymbol] = []
        edges: list[ParsedEdge] = []

        def walk(node: Any) -> None:
            if node.type == "function_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    func_name = name_node.text.decode("utf-8")
                    symbols.append(
                        ParsedSymbol(
                            name=func_name,
                            kind="function",
                            line=node.start_point[0] + 1,
                            column=node.start_point[1],
                            end_line=node.end_point[0] + 1,
                            container=None,
                            docstring=self._extract_docstring(node, content),
                            signature=None,
                            is_exported=func_name[0].isupper(),
                            content_snippet=self._snippet(node),
                        )
                    )
                    edges.extend(self._extract_calls(node, func_name, file_path))

            elif node.type == "method_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    method_name = name_node.text.decode("utf-8")
                    symbols.append(
                        ParsedSymbol(
                            name=method_name,
                            kind="method",
                            line=node.start_point[0] + 1,
                            column=node.start_point[1],
                            end_line=node.end_point[0] + 1,
                            container=None,
                            docstring=None,
                            signature=None,
                            is_exported=method_name[0].isupper(),
                            content_snippet=self._snippet(node),
                        )
                    )

            for child in node.children:
                walk(child)

        walk(root)
        return symbols, edges

    def _extract_rust(
        self, file_path: str, content: str, root: Any
    ) -> tuple[list[ParsedSymbol], list[ParsedEdge]]:
        """Extract symbols from Rust AST."""

        symbols: list[ParsedSymbol] = []
        edges: list[ParsedEdge] = []

        def walk(node: Any) -> None:
            if node.type == "function_item":
                name_node = node.child_by_field_name("name")
                if name_node:
                    func_name = name_node.text.decode("utf-8")
                    symbols.append(
                        ParsedSymbol(
                            name=func_name,
                            kind="function",
                            line=node.start_point[0] + 1,
                            column=node.start_point[1],
                            end_line=node.end_point[0] + 1,
                            container=None,
                            docstring=self._extract_docstring(node, content),
                            signature=None,
                            is_exported=True,
                            content_snippet=self._snippet(node),
                        )
                    )
                    edges.extend(self._extract_calls(node, func_name, file_path))

            elif node.type == "struct_item":
                name_node = node.child_by_field_name("name")
                if name_node:
                    struct_name = name_node.text.decode("utf-8")
                    symbols.append(
                        ParsedSymbol(
                            name=struct_name,
                            kind="class",
                            line=node.start_point[0] + 1,
                            column=node.start_point[1],
                            end_line=node.end_point[0] + 1,
                            container=None,
                            docstring=None,
                            signature=None,
                            is_exported=True,
                            content_snippet=self._snippet(node),
                        )
                    )

            for child in node.children:
                walk(child)

        walk(root)
        return symbols, edges

    def _extract_java(
        self, file_path: str, content: str, root: Any
    ) -> tuple[list[ParsedSymbol], list[ParsedEdge]]:
        """Extract symbols from Java AST."""

        symbols: list[ParsedSymbol] = []
        edges: list[ParsedEdge] = []
        current_class: str | None = None

        def walk(node: Any) -> None:
            nonlocal current_class

            if node.type == "class_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    current_class = name_node.text.decode("utf-8")
                    symbols.append(
                        ParsedSymbol(
                            name=current_class,
                            kind="class",
                            line=node.start_point[0] + 1,
                            column=node.start_point[1],
                            end_line=node.end_point[0] + 1,
                            container=None,
                            docstring=None,
                            signature=None,
                            is_exported=True,
                            content_snippet=self._snippet(node),
                        )
                    )

            elif node.type == "method_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    method_name = name_node.text.decode("utf-8")
                    symbols.append(
                        ParsedSymbol(
                            name=method_name,
                            kind="method",
                            line=node.start_point[0] + 1,
                            column=node.start_point[1],
                            end_line=node.end_point[0] + 1,
                            container=current_class,
                            docstring=self._extract_docstring(node, content),
                            signature=None,
                            is_exported=True,
                            content_snippet=self._snippet(node),
                        )
                    )
                    edges.extend(self._extract_calls(node, method_name, file_path))

            for child in node.children:
                walk(child)

            if node.type == "class_declaration":
                current_class = None

        walk(root)
        return symbols, edges

    def _extract_php(
        self, file_path: str, content: str, root: Any
    ) -> tuple[list[ParsedSymbol], list[ParsedEdge]]:
        """Extract symbols from PHP AST via tree-sitter (not hard-routed to regex)."""

        symbols: list[ParsedSymbol] = []
        edges: list[ParsedEdge] = []
        current_class: str | None = None

        def walk(node: Any) -> None:
            nonlocal current_class

            if node.type in ("class_declaration", "interface_declaration", "trait_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    current_class = name_node.text.decode("utf-8")
                    symbols.append(
                        ParsedSymbol(
                            name=current_class,
                            kind="class",
                            line=node.start_point[0] + 1,
                            column=node.start_point[1],
                            end_line=node.end_point[0] + 1,
                            container=None,
                            docstring=None,
                            signature=None,
                            is_exported=True,
                            content_snippet=self._snippet(node),
                        )
                    )

            elif node.type in ("function_definition", "method_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    func_name = name_node.text.decode("utf-8")
                    in_class = node.type == "method_declaration"
                    symbols.append(
                        ParsedSymbol(
                            name=func_name,
                            kind="method" if in_class else "function",
                            line=node.start_point[0] + 1,
                            column=node.start_point[1],
                            end_line=node.end_point[0] + 1,
                            container=current_class if in_class else None,
                            docstring=None,
                            signature=None,
                            is_exported=True,
                            content_snippet=self._snippet(node),
                        )
                    )
                    edges.extend(self._extract_calls(node, func_name, file_path))

            for child in node.children:
                walk(child)

            if node.type in ("class_declaration", "interface_declaration", "trait_declaration"):
                current_class = None

        walk(root)
        return symbols, edges

    def _extract_generic(
        self, file_path: str, content: str, root: Any, language: str
    ) -> tuple[list[ParsedSymbol], list[ParsedEdge]]:
        """Extract declaration-level symbols for a loaded grammar with no dedicated extractor.

        Handles c, cpp, ruby, csharp (and best-effort kotlin/swift): walks the
        AST and, for every node whose type is in the language's
        :data:`_GENERIC_SYMBOL_NODE_TYPES` set, emits a :class:`ParsedSymbol`.
        The name is read from the ``name`` field where the grammar provides it
        (ruby/csharp/cpp-classes/c-structs); C/C++ functions and C ``typedef``s
        keep the name inside a ``declarator`` subtree, so this descends to the
        innermost identifier as a fallback. Edges are intentionally not produced
        for generic languages — symbols are the priority and a wrong/partial
        edge is worse than none. Container tracking is a lightweight stack of the
        enclosing type/namespace so methods get a sensible ``container``.
        """

        symbol_types = _GENERIC_SYMBOL_NODE_TYPES.get(language)
        if not symbol_types:
            return [], []

        symbols: list[ParsedSymbol] = []
        # A node type is "container-like" if it can hold nested declarations.
        container_kinds = {"class", "struct", "interface", "enum", "namespace", "module"}

        def descend_declarator(node: Any) -> str | None:
            """Innermost identifier of a C/C++ declarator subtree (function/typedef name)."""
            if node.type in ("identifier", "field_identifier", "type_identifier"):
                return str(node.text.decode("utf-8", errors="replace"))
            for child in node.children:
                found = descend_declarator(child)
                if found is not None:
                    return found
            return None

        def name_of(node: Any) -> str | None:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                return str(name_node.text.decode("utf-8", errors="replace"))
            declarator = node.child_by_field_name("declarator")
            if declarator is not None:
                return descend_declarator(declarator)
            return None

        def walk(node: Any, container: str | None) -> None:
            next_container = container
            if node.type in symbol_types:
                name = name_of(node)
                if name:
                    kind = _GENERIC_KIND_BY_TYPE.get(node.type, "symbol")
                    # A bare function inside a container reads as a method; a
                    # container-kind node becomes the container for its children.
                    if kind == "function" and container is not None:
                        kind = "method"
                    symbols.append(
                        ParsedSymbol(
                            name=name,
                            kind=kind,
                            line=node.start_point[0] + 1,
                            column=node.start_point[1],
                            end_line=node.end_point[0] + 1,
                            container=container if kind in ("method", "function") else None,
                            docstring=None,
                            signature=None,
                            # Ruby/C: leading-underscore/lowercase isn't a
                            # reliable export signal across these langs, so index
                            # every top-level declaration as visible.
                            is_exported=True,
                            content_snippet=self._snippet(node),
                        )
                    )
                    if kind in container_kinds and name:
                        next_container = name

            for child in node.children:
                walk(child, next_container)

        walk(root, None)
        return symbols, []

    def _snippet(self, node: Any, max_chars: int = 400) -> str | None:
        """Return up to max_chars of the node's raw source text for FTS indexing."""
        try:
            text: str = node.text.decode("utf-8", errors="replace")[:max_chars]
            return text
        except Exception:
            return None

    def _extract_docstring(self, node: Any, content: str) -> str | None:
        """Extract the docstring of a Python function/class node, if any.

        The docstring is the first statement of the body, nested as
        ``def/class -> block -> expression_statement -> string`` — it is NOT a
        direct child of ``node``, so a child-scan finds nothing.
        """

        body = node.child_by_field_name("body")
        if body is None:
            for child in node.children:
                if child.type == "block":
                    body = child
                    break
        if body is None:
            return None

        for stmt in body.children:
            if not getattr(stmt, "is_named", True) or stmt.type == "comment":
                continue
            # Only the first real statement can be a docstring.
            if stmt.type != "expression_statement":
                return None
            for sub in stmt.children:
                if sub.type == "string":
                    # Prefer the string_content child (no quote delimiters) over
                    # stripping quote chars, which over-strips interior quotes.
                    for piece in sub.children:
                        if piece.type == "string_content":
                            return str(piece.text.decode("utf-8", errors="replace"))
                    raw = str(sub.text.decode("utf-8", errors="replace")).strip()
                    for quote in ('"""', "'''", '"', "'"):
                        q = len(quote)
                        if raw.startswith(quote) and raw.endswith(quote) and len(raw) >= 2 * q:
                            return raw[q:-q]
                    return raw
            return None
        return None

    def _extract_signature(self, node: Any, content: str) -> str | None:
        """Extract function signature from a node."""

        parameters = node.child_by_field_name("parameters")
        if parameters:
            return str(parameters.text.decode("utf-8"))
        return None

    def _extract_calls(self, node: Any, caller_name: str, file_path: str) -> list[ParsedEdge]:
        """Extract call edges from within a function/method body."""

        edges: list[ParsedEdge] = []

        def walk_calls(child: Any) -> None:
            # Python uses "call"; JS/TS/Go/Rust use "call_expression"; PHP uses
            # "function_call_expression" — all expose the callee on a "function"
            # field, so they share one path.
            if child.type in ("call", "call_expression", "function_call_expression"):
                func_node = child.child_by_field_name("function")
                if func_node:
                    target = func_node.text.decode("utf-8")
                    receiver: str | None = None
                    attr = target
                    # Decompose attribute/method targets: receiver.attr(...)
                    if func_node.type in (
                        "attribute",
                        "member_expression",
                        "field_expression",
                        "member_access_expression",  # PHP $obj->method(...)
                    ):
                        obj_node = func_node.child_by_field_name(
                            "object"
                        ) or func_node.child_by_field_name("argument")
                        attr_node = (
                            func_node.child_by_field_name("attribute")
                            or func_node.child_by_field_name("field")
                            or func_node.child_by_field_name("name")  # PHP member access
                        )
                        if attr_node is not None:
                            attr = attr_node.text.decode("utf-8")
                        if obj_node is not None:
                            receiver = obj_node.text.decode("utf-8")
                    if "." in attr and receiver is None:
                        # Fallback decomposition from the raw dotted text.
                        receiver, attr = attr.rsplit(".", 1)
                    edges.append(
                        ParsedEdge(
                            source_name=caller_name,
                            target_name=target,
                            kind="calls",
                            call_site_line=child.start_point[0] + 1,
                            attr=attr,
                            receiver=receiver,
                        )
                    )

            # Java "method_invocation" is shaped differently: the callee is on a
            # "name" field and the (optional) receiver on an "object" field, with
            # no single "function" node — so it gets its own branch.
            elif child.type == "method_invocation":
                name_node = child.child_by_field_name("name")
                if name_node is not None:
                    attr = name_node.text.decode("utf-8")
                    obj_node = child.child_by_field_name("object")
                    receiver = obj_node.text.decode("utf-8") if obj_node is not None else None
                    target = f"{receiver}.{attr}" if receiver else attr
                    edges.append(
                        ParsedEdge(
                            source_name=caller_name,
                            target_name=target,
                            kind="calls",
                            call_site_line=child.start_point[0] + 1,
                            attr=attr,
                            receiver=receiver,
                        )
                    )

            for sub in child.children:
                walk_calls(sub)

        # Walk children, skipping the function's own definition
        for child in node.children:
            if child.type not in ("function_definition", "async_function_definition"):
                walk_calls(child)

        return edges
