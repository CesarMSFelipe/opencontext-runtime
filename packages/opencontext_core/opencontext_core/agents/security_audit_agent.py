"""Security audit agent — runs security gates on context."""

from __future__ import annotations

import re
from typing import Any

from opencontext_core.agents.base import BaseAgent

# Simple secret patterns — no external deps
_SECRET_PATTERNS = [
    re.compile(
        r'(?i)(api[_-]?key|secret|password|token|private[_-]?key)\s*[=:]\s*["\']?[\w\-]{8,}'
    ),
    re.compile(r"[A-Z0-9]{20,40}"),  # generic long uppercase tokens
    re.compile(r"-----BEGIN [A-Z ]+-----"),  # PEM keys
]


class SecurityAuditAgent(BaseAgent):
    """Scans files for secret leakage patterns. Pure local."""

    async def execute(self) -> dict[str, Any]:
        scope = self.config.scope or {}
        paths = scope.get("paths", ["."])
        findings = []
        for path_str in paths:
            path = self.project_root / path_str
            for f in path.rglob("*.py") if path.is_dir() else [path]:
                try:
                    content = f.read_text(errors="ignore")
                    for pattern in _SECRET_PATTERNS:
                        for m in pattern.finditer(content):
                            findings.append(
                                {
                                    "file": str(f.relative_to(self.project_root)),
                                    "line": content[: m.start()].count("\n") + 1,
                                    "match": m.group(0)[:60],
                                }
                            )
                except (OSError, PermissionError):
                    continue
        return {
            "findings": findings,
            "finding_count": len(findings),
            "clean": len(findings) == 0,
        }
