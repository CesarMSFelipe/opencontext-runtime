"""Local manifest-based retrieval."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.models.context import ContextItem, ContextPriority
from opencontext_core.models.project import FileKind, ProjectFile, ProjectManifest, Symbol
from opencontext_core.retrieval.ranking import RetrievalScorer


class ProjectRetriever:
    """Retrieves context from a local project manifest and working tree."""

    def __init__(self, manifest: ProjectManifest) -> None:
        self.manifest = manifest
        self.scorer = RetrievalScorer()

    def retrieve(self, query: str, top_k: int) -> list[ContextItem]:
        """Retrieve file and symbol context candidates."""

        terms = self.scorer.terms(query)
        symbols_by_path = _symbols_by_path(self.manifest.symbols)
        candidates: list[ContextItem] = []
        candidates.extend(self._retrieve_files(terms, symbols_by_path))
        candidates.extend(self._retrieve_symbols(terms))
        candidates = [candidate for candidate in candidates if candidate.score > 0]
        if not candidates:
            candidates = self._fallback_candidates()
        return sorted(candidates, key=lambda item: (-item.score, item.tokens, item.id))[:top_k]

    def _retrieve_files(
        self,
        terms: list[str],
        symbols_by_path: dict[str, list[Symbol]],
    ) -> list[ContextItem]:
        items: list[ContextItem] = []
        for file in self.manifest.files:
            if file.file_type is FileKind.ASSET:
                continue
            score, match_metadata = self.scorer.file_score(
                terms,
                file,
                symbols_by_path.get(file.path, []),
            )
            # Only read+redact files that actually matched the query. Reading and
            # secret/PII-scanning every file in the repo (most scoring 0) was the
            # dominant cost; non-matching files never reach the pack anyway.
            if score <= 0:
                continue
            content, redacted = self._read_file_content(file)
            if not content:
                content = file.summary
            metadata = {
                **file.metadata,
                "retrieval": match_metadata,
                "retrieval_rationale": _build_rationale("file", match_metadata),
                "file_type": file.file_type.value,
                "language": file.language,
                "summary": file.summary,
                "redacted": redacted,
            }
            items.append(
                ContextItem(
                    id=f"file:{file.path}",
                    content=content,
                    source=file.path,
                    source_type="file",
                    priority=_priority_for_file(file),
                    tokens=estimate_tokens(content),
                    score=score,
                    metadata=metadata,
                )
            )
        return items

    def _retrieve_symbols(self, terms: list[str]) -> list[ContextItem]:
        items: list[ContextItem] = []
        for symbol in self.manifest.symbols:
            score, match_metadata = self.scorer.symbol_score(terms, symbol)
            if score <= 0:
                continue
            snippet, redacted = self._read_symbol_snippet(symbol)
            content = (
                f"{symbol.kind} {symbol.name} in {symbol.path}:{symbol.line}\n{snippet}".strip()
            )
            items.append(
                ContextItem(
                    id=f"symbol:{symbol.id}",
                    content=content,
                    source=f"{symbol.path}:{symbol.line}",
                    source_type="symbol",
                    priority=ContextPriority.P1,
                    tokens=estimate_tokens(content),
                    score=score,
                    metadata={
                        "retrieval": match_metadata,
                        "retrieval_rationale": _build_rationale("symbol", match_metadata),
                        "symbol_kind": symbol.kind,
                        "language": symbol.language,
                        "container": symbol.container,
                        "redacted": redacted,
                    },
                )
            )
        return items

    def _fallback_candidates(self) -> list[ContextItem]:
        items: list[ContextItem] = []
        for file in self.manifest.files[:10]:
            if file.file_type is FileKind.ASSET:
                continue
            content, redacted = self._read_file_content(file)
            if not content:
                content = file.summary
            items.append(
                ContextItem(
                    id=f"file:{file.path}",
                    content=content,
                    source=file.path,
                    source_type="file",
                    priority=_priority_for_file(file),
                    tokens=estimate_tokens(content),
                    score=0.05,
                    metadata={
                        **file.metadata,
                        "retrieval": {"fallback": True},
                        "retrieval_rationale": ["fallback:manifest_top_files"],
                        "file_type": file.file_type.value,
                        "language": file.language,
                        "summary": file.summary,
                        "redacted": redacted,
                    },
                )
            )
        return items

    def _read_file_content(self, file: ProjectFile) -> tuple[str, bool]:
        # Read RAW for candidate ranking. Redaction is deferred to the selected
        # pack items (see RetrievalPlanner), so secret/PII scanning runs over the
        # ~top-k delivered files, not every candidate in the repo. Dropped
        # candidates are never delivered, so reading them raw is safe.
        path = Path(self.manifest.root) / file.path
        if not path.exists() or not path.is_file():
            return file.summary, False
        raw = path.read_bytes()
        if b"\x00" in raw[:2048]:
            return file.summary, False
        return raw[:120_000].decode("utf-8", errors="ignore"), False

    def _read_symbol_snippet(self, symbol: Symbol) -> tuple[str, bool]:
        path = Path(self.manifest.root) / symbol.path
        if not path.exists() or not path.is_file():
            return "", False
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        # end_line stored in metadata by extractor (AST-aware chunking)
        end_line: int | None = symbol.metadata.get("end_line")
        start = max(0, symbol.line - 1)  # 0-based
        if end_line is not None:
            end = min(len(lines), end_line)
        else:
            # Heuristic: scan forward from definition until indentation drops back
            # (handles Python/PHP without requiring tree-sitter at retrieval time)
            end = _find_block_end(lines, start, max_lines=120)
        return "\n".join(lines[start:end]), False


def _find_block_end(lines: list[str], start: int, *, max_lines: int = 120) -> int:
    """Return the 0-based exclusive end index of the code block starting at `start`.

    Uses indentation level of the definition line to detect when the block ends.
    Falls back to start+8 for files with no clear indentation structure.
    """
    if start >= len(lines):
        return start + 1
    def_line = lines[start]
    base_indent = len(def_line) - len(def_line.lstrip())
    limit = min(len(lines), start + max_lines)
    for i in range(start + 1, limit):
        line = lines[i]
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= base_indent and line.strip() and not line.strip().startswith("#"):
            return i
    return limit


def _symbols_by_path(symbols: list[Symbol]) -> dict[str, list[Symbol]]:
    by_path: dict[str, list[Symbol]] = {}
    for symbol in symbols:
        by_path.setdefault(symbol.path, []).append(symbol)
    return by_path


def _priority_for_file(file: ProjectFile) -> ContextPriority:
    priorities = {
        FileKind.CODE: ContextPriority.P1,
        FileKind.CONFIG: ContextPriority.P2,
        FileKind.TEST: ContextPriority.P2,
        FileKind.DOCUMENTATION: ContextPriority.P3,
        FileKind.TEMPLATE: ContextPriority.P3,
        FileKind.UNKNOWN: ContextPriority.P5,
        FileKind.ASSET: ContextPriority.P5,
    }
    return priorities[file.file_type]


def _build_rationale(source_type: str, retrieval: dict[str, object]) -> list[str]:
    rationale = [f"source_type:{source_type}"]
    for key in sorted(retrieval):
        value = retrieval[key]
        if isinstance(value, (str, int, float, bool)):
            rationale.append(f"{key}:{value}")
    return rationale
