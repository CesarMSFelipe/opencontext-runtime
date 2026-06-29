"""PROD-005 / B5 — ADR section guard for doc-18.

The Architecture Decision Records document
(``docs/.../18-architecture-decision-records.md``) defines the ADR template every
decision must follow. This guard asserts the document exists and that its required
ADR sections — ``Status``, ``Context``, ``Decision``, ``Consequences`` — are present
AND non-empty. A missing or empty required section fails the test, naming the
offending section, so the ADR structure cannot silently rot.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ADR_DOC = (
    REPO_ROOT
    / "docs/OpenContext_Complete_Plans_and_Architecture_Book"
    / "18-architecture-decision-records.md"
)

#: Sections the ADR template MUST carry, each with non-empty content (book §6).
REQUIRED_SECTIONS = ("Status", "Context", "Decision", "Consequences")

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def _section_bodies(text: str) -> dict[str, str]:
    """Map each markdown heading title → the body text until the next heading."""
    bodies: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            if current is not None and current not in bodies:
                bodies[current] = "\n".join(buf).strip()
            current = m.group(2).strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None and current not in bodies:
        bodies[current] = "\n".join(buf).strip()
    return bodies


def test_adr_doc_exists() -> None:
    """The ADR document (doc-18) must exist."""
    assert ADR_DOC.is_file(), f"ADR document missing: {ADR_DOC}"


def test_adr_required_sections_present_and_non_empty() -> None:
    """Every required ADR section is present and has non-empty content."""
    bodies = _section_bodies(ADR_DOC.read_text(encoding="utf-8"))
    for section in REQUIRED_SECTIONS:
        assert section in bodies, f"ADR section missing: {section!r}"
        assert bodies[section], f"ADR section is empty: {section!r}"
