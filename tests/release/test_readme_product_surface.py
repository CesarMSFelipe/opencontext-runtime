"""README product-surface gate (Amendment-2 / DoD #12).

The README must show the product surface through the real demo recordings
under ``docs/assets/`` — the actual TUI/config/graph screens, not stylized
mockups. Each referenced recording must exist and be non-empty. This keeps the
"show the real product" contract truthful and concise (one proof per screen,
the real one).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# The real product-surface recordings the README must show.
CANONICAL_DEMOS: frozenset[str] = frozenset(
    {
        "docs/assets/demo-menu.gif",
        "docs/assets/demo-config.gif",
        "docs/assets/demo-graph.gif",
    }
)

REPO_ROOT = Path(__file__).resolve().parents[2]
README_PATH = REPO_ROOT / "README.md"


def _readme_text() -> str:
    assert README_PATH.exists(), f"README.md not found at {README_PATH}"
    return README_PATH.read_text(encoding="utf-8")


def _referenced_gifs(readme: str) -> set[str]:
    """Extract ``docs/assets/*.gif`` references from README markdown."""
    return set(re.compile(r"docs/assets/[A-Za-z0-9_.-]+\.gif").findall(readme))


def test_readme_references_all_product_surface_demos() -> None:
    """README references every canonical product-surface recording."""
    referenced = _referenced_gifs(_readme_text())
    missing = CANONICAL_DEMOS - referenced
    assert not missing, f"README is missing product-surface recordings: {missing!r}"


def test_each_demo_exists_and_is_nonempty() -> None:
    """Each canonical demo recording exists under docs/assets/ and is >1KB."""
    for relpath in CANONICAL_DEMOS:
        full = REPO_ROOT / relpath
        assert full.exists(), f"missing demo recording: {relpath}"
        size = full.stat().st_size
        assert size > 1024, f"demo recording too small ({size} bytes): {relpath}"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-x"]))
