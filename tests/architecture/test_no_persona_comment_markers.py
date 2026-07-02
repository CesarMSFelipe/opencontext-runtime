"""Architecture guard: no persona comment markers in production package source.

Sweeping ``# ponytail:`` and ``# caveman:`` to ``# NOTE:`` is the convention
(doc ``forbidden-names-in-code``). This test enforces the convention so new
markers cannot be silently added.

Scope: packages/**/*.py, excluding any ``/tests/`` and ``/build/`` subtrees.
"""

from __future__ import annotations

from pathlib import Path

# Repo root is two levels up from this file (tests/architecture/).
_REPO_ROOT = Path(__file__).parent.parent.parent
_PACKAGES_DIR = _REPO_ROOT / "packages"

_FORBIDDEN_MARKERS = ("# ponytail:", "# caveman:")


def _production_sources() -> list[Path]:
    """Return all .py files under packages/ excluding tests/ and build/ trees."""
    sources: list[Path] = []
    for path in _PACKAGES_DIR.rglob("*.py"):
        parts = path.parts
        if "tests" in parts or "build" in parts:
            continue
        sources.append(path)
    return sources


def test_no_persona_comment_markers_in_production_source() -> None:
    """No production source file should contain ``# ponytail:`` or ``# caveman:``."""
    violations: list[str] = []
    for path in _production_sources():
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for marker in _FORBIDDEN_MARKERS:
                if marker in line:
                    rel = path.relative_to(_REPO_ROOT)
                    violations.append(f"{rel}:{lineno}: {line.strip()!r}")

    assert not violations, (
        f"Found {len(violations)} forbidden persona comment marker(s) in production source.\n"
        "Replace with '# NOTE:' preserving the rest of the comment text.\n\n"
        + "\n".join(violations[:30])
    )
