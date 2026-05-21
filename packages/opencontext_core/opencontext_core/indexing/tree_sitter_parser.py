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


@dataclass
class ParsedEdge:
    """A relationship edge extracted from source code."""

    source_name: str
    target_name: str
    kind: str
    call_site_line: int | None


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
            from tree_sitter import Parser  # type: ignore[import-not-found]

            self._available = True
            self._parser_class = Parser

            # Try to load common language grammars
            self._load_language("python", "tree_sitter_python")
            self._load_language("javascript", "tree_sitter_javascript")
            self._load_language("typescript", "tree_sitter_typescript")
            self._load_language("go", "tree_sitter_go")
            self._load_language("rust", "tree_sitter_rust")
            self._load_language("java", "tree_sitter_java")
            self._load_language("php", "tree_sitter_php")
            self._load_language("c", "tree_sitter_c")
            self._load_language("cpp", "tree_sitter_cpp")
            self._load_language("ruby", "tree_sitter_ruby")
            self._load_language("swift", "tree_sitter_swift")
            self._load_language("kotlin", "tree_sitter_kotlin")

        except ImportError:
            self._available = False

        # Fallback to existing regex extractor
        if not self._available:
            from opencontext_core.indexing.symbol_extractor import SymbolExtractor

            self._fallback_parser = SymbolExtractor()

    def _load_language(self, name: str, module_name: str) -> bool:
        """Attempt to load a tree-sitter language grammar."""

        if not self._available:
            return False

        try:
            module = __import__(module_name)
            language_capsule = module.language()
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

        language = self.detect_language(file_path)
        if language is None:
            return [], []

        # Use tree-sitter if available and language grammar loaded
        if self._available and language in self._languages:
            return self._parse_with_tree_sitter(file_path, content, language)

        # Fallback to regex-based extraction for Python/PHP
        return self._parse_with_fallback(file_path, content, language)

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
        """Extract symbols from PHP AST."""

        # PHP parsing with tree-sitter is complex; fallback to regex for now
        return self._parse_with_fallback(file_path, content, "php")

    def _extract_docstring(self, node: Any, content: str) -> str | None:
        """Extract docstring from a node."""

        # Look for string literal or comment after the node
        for child in node.children:
            if child.type in ("string", "expression_statement"):
                text = str(child.text.decode("utf-8")).strip()
                if text.startswith('"""') or text.startswith("'''"):
                    return text.strip('"').strip("'")
                # Expression statement might contain a string
                if child.type == "expression_statement":
                    for sub in child.children:
                        if sub.type == "string":
                            text = str(sub.text.decode("utf-8")).strip()
                            return text.strip('"').strip("'")

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
            if child.type == "call":
                func_node = child.child_by_field_name("function")
                if func_node:
                    target = func_node.text.decode("utf-8")
                    edges.append(
                        ParsedEdge(
                            source_name=caller_name,
                            target_name=target,
                            kind="calls",
                            call_site_line=child.start_point[0] + 1,
                        )
                    )

            for sub in child.children:
                walk_calls(sub)

        # Walk children, skipping the function's own definition
        for child in node.children:
            if child.type not in ("function_definition", "async_function_definition"):
                walk_calls(child)

        return edges
