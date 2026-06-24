"""RequirementsQualityGate — validate spec blocks against EARS / BDD patterns.

A spec file is parsed into per-requirement blocks (split on ``### Requirement:``
headings). Each block must contain at least one acceptance criterion:

  * EARS — ``WHEN … THEN`` or ``IF … THEN``
  * BDD  — ``Given … When … Then``

Returns a ``GateResult(status, errors)`` reusing ``GateStatus`` from
``opencontext_core.harness.models``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from opencontext_core.harness.models import GateStatus

_REQ_HEADING_RE = re.compile(r"^###\s+Requirement:\s*(\S+)", re.MULTILINE)
_EARS_RE = re.compile(r"\b(WHEN|IF)\b.*\bTHEN\b", re.IGNORECASE | re.DOTALL)
_BDD_RE = re.compile(r"\bGiven\b.*\bWhen\b.*\bThen\b", re.IGNORECASE | re.DOTALL)


@dataclass
class GateResult:
    """Outcome of a quality-gate evaluation."""

    status: GateStatus
    errors: list[str] = field(default_factory=list)


class RequirementsQualityGate:
    """Validate spec text against EARS / BDD acceptance patterns."""

    id = "requirements_quality"

    def evaluate(self, spec_text: str) -> GateResult:
        """Return ``GateResult`` for *spec_text*.

        Per-requirement blocks lacking both EARS and BDD keywords produce
        a single error like ``REQ-03: missing WHEN…THEN or Given/When/Then``.
        """
        blocks = self._split_requirements(spec_text)
        if not blocks:
            return GateResult(status=GateStatus.PASSED, errors=[])

        errors: list[str] = []
        for req_id, body in blocks:
            if self._ears_ok(body) or self._bdd_ok(body):
                continue
            errors.append(
                f"{req_id}: missing WHEN…THEN or Given/When/Then acceptance criterion"
            )

        status = GateStatus.PASSED if not errors else GateStatus.FAILED
        return GateResult(status=status, errors=errors)

    @staticmethod
    def _split_requirements(spec_text: str) -> list[tuple[str, str]]:
        """Split *spec_text* on ``### Requirement:`` headings."""
        if not spec_text.strip():
            return []
        matches = list(_REQ_HEADING_RE.finditer(spec_text))
        if not matches:
            return []
        blocks: list[tuple[str, str]] = []
        for idx, m in enumerate(matches):
            req_id = m.group(1)
            start = m.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(spec_text)
            blocks.append((req_id, spec_text[start:end]))
        return blocks

    @staticmethod
    def _ears_ok(body: str) -> bool:
        return bool(_EARS_RE.search(body))

    @staticmethod
    def _bdd_ok(body: str) -> bool:
        return bool(_BDD_RE.search(body))