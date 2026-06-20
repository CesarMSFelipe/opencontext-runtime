"""Filesystem scanner for the project intelligence layer."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path

from opencontext_core.compat import UTC
from opencontext_core.config import DEFAULT_IGNORE_PATTERNS
from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.indexing.classifier import classify_file, detect_language
from opencontext_core.indexing.symbol_extractor import ExtractableFile, SymbolExtractor
from opencontext_core.models.project import FileKind, ProjectFile, Symbol
from opencontext_core.safety.secrets import SecretScanner

MAX_TEXT_READ_BYTES = 1_000_000


@dataclass(frozen=True)
class ScannedFile:
    """Text and metadata captured for one scanned file."""

    path: Path
    relative_path: str
    language: str
    file_type: FileKind
    content: str
    tokens: int
    size_bytes: int
    summary: str
    metadata: dict[str, str | bool]

    def to_project_file(self) -> ProjectFile:
        """Convert the scanned file into a manifest model."""

        return ProjectFile(
            id=self.relative_path,
            path=self.relative_path,
            language=self.language,
            file_type=self.file_type,
            tokens=self.tokens,
            size_bytes=self.size_bytes,
            summary=self.summary,
            metadata=dict(self.metadata),
        )


def is_ignored(path: Path, root: Path, ignore_patterns: list[str]) -> bool:
    """Return whether a path is ignored by project-relative patterns."""

    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        relative = path.as_posix()

    parts = set(Path(relative).parts)
    for pattern in ignore_patterns:
        raw = pattern.strip()
        anchored = raw.startswith("/")  # gitignore: leading slash anchors to root
        normalized = raw.strip("/")
        if not normalized:
            continue
        if anchored:
            # Anchored patterns match only at the repo root, not nested occurrences:
            # '/build' ignores top-level build/ but not src/build/.
            if relative == normalized or relative.startswith(f"{normalized}/"):
                return True
            if fnmatch(relative, normalized):
                return True
            continue
        if normalized in parts:
            return True
        if relative == normalized or relative.startswith(f"{normalized}/"):
            return True
        if fnmatch(relative, normalized) or fnmatch(path.name, normalized):
            return True
    return False


class ProjectScanner:
    """Scans a project tree into deterministic file metadata."""

    def __init__(self, ignore_patterns: list[str] | None = None) -> None:
        self.ignore_patterns = list(ignore_patterns or DEFAULT_IGNORE_PATTERNS)
        self.secret_scanner = SecretScanner()
        self.symbol_extractor = SymbolExtractor()

    def scan(self, root: Path) -> list[ScannedFile]:
        """Scan a project root and return indexed files."""

        resolved_root = root.resolve()
        effective_ignores = self._effective_ignore_patterns(resolved_root)
        scanned: list[ScannedFile] = []
        for current_root, directory_names, file_names in os.walk(resolved_root):
            current_path = Path(current_root)
            directory_names[:] = sorted(
                name
                for name in directory_names
                if not is_ignored(current_path / name, resolved_root, effective_ignores)
            )
            for file_name in sorted(file_names):
                file_path = current_path / file_name
                if is_ignored(file_path, resolved_root, effective_ignores):
                    continue
                if not file_path.is_file():
                    continue
                scanned.append(self._scan_file(file_path, resolved_root))
        return scanned

    def _effective_ignore_patterns(self, root: Path) -> list[str]:
        patterns = list(self.ignore_patterns)
        for ignore_file in (root / ".gitignore", root / ".opencontextignore"):
            if not ignore_file.exists() or not ignore_file.is_file():
                continue
            for line in ignore_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                normalized = line.strip()
                if not normalized or normalized.startswith("#"):
                    continue
                patterns.append(normalized)
        return list(dict.fromkeys(patterns))

    def _scan_file(self, path: Path, root: Path) -> ScannedFile:
        relative_path = path.relative_to(root).as_posix()
        size_bytes = path.stat().st_size
        language = detect_language(Path(relative_path))
        file_type = classify_file(Path(relative_path))
        content, truncated = _read_text(path)
        secret_findings = self.secret_scanner.scan(content) if content else []
        indexed_content = self.secret_scanner.redact(content) if secret_findings else content
        tokens = estimate_tokens(indexed_content) if indexed_content else max(1, size_bytes // 4)
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()

        # Extract symbols for enrichment
        symbols = []
        if indexed_content and language in {"python", "php"}:
            symbols = self.symbol_extractor.extract(
                ExtractableFile(
                    relative_path=relative_path,
                    language=language,
                    content=indexed_content,
                )
            )

        summary = summarize_file(
            relative_path, language, file_type, tokens, indexed_content, symbols
        )
        metadata: dict[str, str | bool] = {
            "modified_at": modified_at,
            "truncated_at_indexing": truncated,
            "symbol_count": str(len(symbols)),
        }
        if secret_findings:
            metadata["contains_potential_secrets"] = True
            metadata["safety_warning"] = "potential secrets detected and redacted from context"
            metadata["secret_finding_kinds"] = ",".join(
                sorted({finding.kind for finding in secret_findings})
            )
        return ScannedFile(
            path=path,
            relative_path=relative_path,
            language=language,
            file_type=file_type,
            content=indexed_content,
            tokens=tokens,
            size_bytes=size_bytes,
            summary=summary,
            metadata=metadata,
        )


def summarize_file(
    relative_path: str,
    language: str,
    file_type: FileKind,
    tokens: int,
    content: str,
    symbols: list[Symbol] | None = None,
) -> str:
    """Generate a deterministic basic file summary."""

    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    first_line_part = f" First content: {first_line[:120]}" if first_line else ""

    summary = (
        f"{relative_path} is a {language} {file_type.value} file with "
        f"approximately {tokens} tokens.{first_line_part}"
    )

    if symbols:
        important_symbols = [s.name for s in symbols if s.kind in {"class", "interface", "trait"}]
        if not important_symbols:
            important_symbols = [s.name for s in symbols][:5]

        if important_symbols:
            summary += f" Key symbols: {', '.join(important_symbols[:10])}."

    return summary


def _read_text(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    if b"\x00" in raw[:2048]:
        return "", False
    truncated = len(raw) > MAX_TEXT_READ_BYTES
    return raw[:MAX_TEXT_READ_BYTES].decode("utf-8", errors="ignore"), truncated
