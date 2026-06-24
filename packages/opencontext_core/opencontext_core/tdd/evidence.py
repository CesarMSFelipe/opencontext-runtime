"""TDDEvidenceReport — trace requirement ids to test files.

For each requirement id (e.g. ``REQ-01``), find every test file under
``tests_root`` whose source text mentions that id. Build a flat report so
reviewers can see which requirements have NO test coverage yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_REQ_TOKEN_RE = re.compile(r"REQ-?\d+", re.IGNORECASE)


@dataclass
class RequirementEvidence:
    """Coverage evidence for one requirement."""

    req_id: str
    covered: bool
    test_paths: list[str] = field(default_factory=list)


@dataclass
class TDDEvidenceReport:
    """Aggregated coverage evidence for a set of requirements."""

    entries: list[RequirementEvidence] = field(default_factory=list)

    @property
    def uncovered(self) -> list[RequirementEvidence]:
        return [e for e in self.entries if not e.covered]

    @property
    def covered(self) -> list[RequirementEvidence]:
        return [e for e in self.entries if e.covered]

    @classmethod
    def build(
        cls,
        requirements: list[str],
        tests_root: Path | str,
    ) -> TDDEvidenceReport:
        """Return a report of coverage for *requirements*.

        Searches every ``*.py`` file under ``tests_root`` recursively. A
        requirement is considered *covered* if any test file mentions its
        token (e.g. ``REQ-01``).
        """
        root = Path(tests_root)
        files = list(root.rglob("*.py")) if root.exists() else []

        by_req: dict[str, list[str]] = {req: [] for req in requirements}
        for f in files:
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if not _REQ_TOKEN_RE.search(text):
                continue
            for req in requirements:
                if re.search(rf"\b{re.escape(req)}\b", text, re.IGNORECASE):
                    by_req[req].append(str(f))

        entries = [
            RequirementEvidence(
                req_id=req,
                covered=bool(by_req[req]),
                test_paths=list(by_req[req]),
            )
            for req in requirements
        ]
        return cls(entries=entries)