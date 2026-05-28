"""Cross-language bridge detector — heuristic scan for polyglot call boundaries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CrossLanguageBridge:
    """A detected cross-language call boundary."""

    source_file: str
    source_symbol: str
    target_hint: str
    bridge_type: str  # HTTP | GRPC | CLI_SUBPROCESS | IPC
    confidence: float  # 0.0–1.0
    line: int = 0


_BRIDGE_PATTERNS: list[tuple[str, str, float]] = [
    # (regex, bridge_type, confidence)
    # HTTP clients
    (r"import\s+requests|from\s+requests\s+import|httpx\.", "HTTP", 0.9),
    (r"axios\.(get|post|put|patch|delete|request)\(", "HTTP", 0.9),
    (r"fetch\(['\"]https?://", "HTTP", 0.85),
    (r"http\.Get\(|http\.Post\(|http\.NewRequest\(", "HTTP", 0.85),
    (r"urllib\.request\.(urlopen|urlretrieve)", "HTTP", 0.8),
    # gRPC
    (r"_pb2_grpc\b|grpc\.stub\b|grpc\.channel\b", "GRPC", 0.95),
    (r"grpc\.insecure_channel\(|grpc\.secure_channel\(", "GRPC", 0.95),
    (r"proto\.Marshal\(|proto\.Unmarshal\(", "GRPC", 0.7),
    # CLI subprocess
    (r"subprocess\.(run|Popen|call|check_output)\s*\(\s*\[", "CLI_SUBPROCESS", 0.9),
    (r"child_process\.(exec|spawn|execFile)\(", "CLI_SUBPROCESS", 0.9),
    (r"os\.system\(|os\.popen\(", "CLI_SUBPROCESS", 0.75),
    # IPC
    (r"multiprocessing\.Pipe\(|multiprocessing\.Queue\(", "IPC", 0.8),
    (r"socket\.connect\(|socket\.bind\(", "IPC", 0.7),
]

_SKIP_DIRS: frozenset[str] = frozenset(
    {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox", "dist", "build"}
)
_SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb", ".java", ".cs"}
)


class BridgeDetector:
    """Scans a project for cross-language call bridge heuristics.

    Uses regex pattern matching — no AST parsing. Fast and cross-language.
    Confidence scores are heuristic estimates.
    """

    def __init__(self, max_file_size_bytes: int = 512_000) -> None:
        self._max_size = max_file_size_bytes
        self._compiled = [
            (re.compile(pattern), btype, conf) for pattern, btype, conf in _BRIDGE_PATTERNS
        ]

    def scan(self, root: str | Path = ".") -> list[CrossLanguageBridge]:
        """Scan project root for cross-language bridges.

        Returns a list of detected bridges, sorted by confidence descending.
        """
        root_path = Path(root).resolve()
        bridges: list[CrossLanguageBridge] = []

        for file_path in self._iter_source_files(root_path):
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except (OSError, PermissionError):
                continue
            if len(content) > self._max_size:
                content = content[: self._max_size]

            file_bridges = self._scan_file(file_path, content, root_path)
            bridges.extend(file_bridges)

        bridges.sort(key=lambda b: b.confidence, reverse=True)
        return bridges

    def _scan_file(
        self,
        file_path: Path,
        content: str,
        root: Path,
    ) -> list[CrossLanguageBridge]:
        found: list[CrossLanguageBridge] = []
        rel_path = str(file_path.relative_to(root))
        lines = content.splitlines()

        for i, line in enumerate(lines, start=1):
            for pattern, btype, conf in self._compiled:
                m = pattern.search(line)
                if m:
                    found.append(
                        CrossLanguageBridge(
                            source_file=rel_path,
                            source_symbol="",
                            target_hint=m.group(0)[:80],
                            bridge_type=btype,
                            confidence=conf,
                            line=i,
                        )
                    )
                    break  # one bridge per line

        return found

    def _iter_source_files(self, root: Path):
        """Yield source files, skipping known non-code directories."""
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in _SOURCE_EXTENSIONS:
                if not any(part in _SKIP_DIRS for part in path.parts):
                    yield path
