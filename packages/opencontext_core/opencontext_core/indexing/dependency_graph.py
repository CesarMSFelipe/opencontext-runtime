"""Deterministic static dependency graph extraction."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from opencontext_core.compat import UTC
from opencontext_core.indexing.scanner import ScannedFile
from opencontext_core.models.project import DependencyEdge, DependencyGraph

PY_IMPORT_RE = re.compile(r"^\s*import\s+([A-Za-z0-9_.,\s]+)")
PY_FROM_RE = re.compile(r"^\s*from\s+([A-Za-z0-9_.]+)\s+import\s+")
JS_IMPORT_RE = re.compile(r"\bimport\b.*?\bfrom\s+['\"]([^'\"]+)['\"]")
JS_SIDE_EFFECT_RE = re.compile(r"^\s*import\s+['\"]([^'\"]+)['\"]")
JS_REQUIRE_RE = re.compile(r"\brequire\(['\"]([^'\"]+)['\"]\)")
PHP_USE_RE = re.compile(r"^\s*use\s+([^;]+);")
PHP_INCLUDE_RE = re.compile(
    r"\b(?:require|require_once|include|include_once)\s+['\"]([^'\"]+)['\"]"
)


class DependencyGraphBuilder:
    """Builds a lightweight dependency graph without parser dependencies."""

    def build(self, files: list[ScannedFile]) -> DependencyGraph:
        """Build a dependency graph from scanned files."""

        paths = sorted(file.relative_path for file in files)
        path_set = set(paths)
        edges: list[DependencyEdge] = []
        for file in files:
            edges.extend(self._edges_for_file(file, path_set))
        internal_edges = [edge for edge in edges if edge.internal]
        unresolved = [edge for edge in edges if not edge.internal]
        return DependencyGraph(
            nodes=paths,
            edges=sorted(internal_edges, key=_edge_key),
            unresolved=sorted(unresolved, key=_edge_key),
            generated_at=datetime.now(tz=UTC),
        )

    def _edges_for_file(self, file: ScannedFile, path_set: set[str]) -> list[DependencyEdge]:
        if file.language == "python":
            return _python_edges(file, path_set)
        if file.language in {"javascript", "typescript"}:
            return _js_edges(file, path_set)
        if file.language == "php":
            return _php_edges(file, path_set)
        return []


def _python_edges(file: ScannedFile, path_set: set[str]) -> list[DependencyEdge]:
    edges: list[DependencyEdge] = []
    for line_number, line in enumerate(file.content.splitlines(), start=1):
        import_match = PY_IMPORT_RE.match(line)
        if import_match:
            for module in import_match.group(1).split(","):
                target = module.strip().split(" as ")[0]
                edges.append(_edge(file.relative_path, target, "import", line_number, path_set))
        from_match = PY_FROM_RE.match(line)
        if from_match:
            target = from_match.group(1)
            edges.append(_edge(file.relative_path, target, "from_import", line_number, path_set))
    return edges


def _js_edges(file: ScannedFile, path_set: set[str]) -> list[DependencyEdge]:
    edges: list[DependencyEdge] = []
    for line_number, line in enumerate(file.content.splitlines(), start=1):
        for pattern, kind in (
            (JS_IMPORT_RE, "import"),
            (JS_SIDE_EFFECT_RE, "import"),
            (JS_REQUIRE_RE, "require"),
        ):
            match = pattern.search(line)
            if match:
                edges.append(_edge(file.relative_path, match.group(1), kind, line_number, path_set))
    return edges


def _php_edges(file: ScannedFile, path_set: set[str]) -> list[DependencyEdge]:
    edges: list[DependencyEdge] = []
    for line_number, line in enumerate(file.content.splitlines(), start=1):
        use_match = PHP_USE_RE.match(line)
        if use_match:
            edges.append(
                _edge(file.relative_path, use_match.group(1), "use", line_number, path_set)
            )
        include_match = PHP_INCLUDE_RE.search(line)
        if include_match:
            edges.append(
                _edge(file.relative_path, include_match.group(1), "include", line_number, path_set)
            )
    return edges


def _edge(
    source: str,
    target: str,
    kind: str,
    line: int,
    path_set: set[str],
) -> DependencyEdge:
    resolved = _resolve_target(source, target, path_set)
    return DependencyEdge(
        source=source,
        target=resolved or target,
        kind=kind,
        internal=resolved is not None,
        line=line,
    )


def _resolve_target(source: str, target: str, path_set: set[str]) -> str | None:
    if target in path_set:
        return target
    candidates: list[str] = []
    if target.startswith("."):
        # Python relative import: leading dots = levels up from the source's
        # directory ('.util' -> source_dir/util, '..util' -> parent/util, '.' ->
        # the package itself). Previously this produced 'source_dir/.util' and the
        # module-path branch mangled it, so relative imports never resolved.
        dots = len(target) - len(target.lstrip("."))
        remainder = target[dots:].replace(".", "/")
        base = Path(source).parent
        for _ in range(dots - 1):
            base = base.parent
        stem = (base / remainder).as_posix() if remainder else base.as_posix()
        candidates.extend([f"{stem}.py", f"{stem}/__init__.py", stem])
    else:
        module_path = target.replace(".", "/").replace("\\", "/")
        candidates.extend(
            [
                module_path,
                f"{module_path}.py",
                f"{module_path}.js",
                f"{module_path}.ts",
                f"{module_path}.php",
                f"{module_path}/__init__.py",
                f"{module_path}/index.js",
                f"{module_path}/index.ts",
            ]
        )
    for candidate in candidates:
        normalized = candidate.replace("/./", "/")
        if normalized in path_set:
            return normalized
    return None


def _edge_key(edge: DependencyEdge) -> tuple[str, str, str, int]:
    return (edge.source, edge.target, edge.kind, edge.line)
