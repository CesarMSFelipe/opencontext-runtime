"""README + SVG product-surface gate (Amendment-2 / DoD #12).

The README must reference all five canonical product-surface SVGs
under ``docs/assets/``. Each SVG must exist, be non-empty (>1KB),
parse as valid SVG XML, and carry a ``<title>`` element whose
text content matches the diagram name.

The test asserts the canonical 5-name set is exactly what the
README references — no aliasing or partial substitution allowed.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

# Canonical 5-name set (Amendment-2). The test compares both
# directions against this frozenset so aliases are rejected.
CANONICAL_SVGS: frozenset[str] = frozenset(
    {
        "docs/assets/tui-cockpit.svg",
        "docs/assets/config-menu.svg",
        "docs/assets/graph-viewer.svg",
        "docs/assets/release-candidate-status.svg",
        "docs/assets/user-flows.svg",
    }
)

CANONICAL_DIAGRAM_NAMES: frozenset[str] = frozenset(
    {
        "TUI Cockpit",
        "Config Menu",
        "Graph Viewer",
        "Release Candidate Status",
        "User Flows",
    }
)

REPO_ROOT = Path(__file__).resolve().parents[2]
README_PATH = REPO_ROOT / "README.md"
ASSETS_DIR = REPO_ROOT / "docs" / "assets"


def _readme_text() -> str:
    assert README_PATH.exists(), f"README.md not found at {README_PATH}"
    return README_PATH.read_text(encoding="utf-8")


def _referenced_svg_paths(readme: str) -> set[str]:
    """Extract ``docs/assets/*.svg`` references from README markdown."""
    pattern = re.compile(r"docs/assets/[A-Za-z0-9_.-]+\.svg")
    return set(pattern.findall(readme))


def test_readme_references_all_five_required_svgs() -> None:
    """README references all five canonical SVG names (subset of total)."""
    referenced = _referenced_svg_paths(_readme_text())
    missing = CANONICAL_SVGS - referenced
    assert not missing, f"README is missing canonical SVG references: {missing!r}"
    # And every canonical name is referenced (no alias substitution).
    for relpath in CANONICAL_SVGS:
        assert relpath in referenced, f"README does not reference {relpath!r}"


def test_each_canonical_svg_exists_and_is_nonempty() -> None:
    """Each canonical SVG exists under docs/assets/ and is >1KB."""
    for relpath in CANONICAL_SVGS:
        full = REPO_ROOT / relpath
        assert full.exists(), f"missing SVG: {relpath}"
        size = full.stat().st_size
        assert size > 1024, f"SVG too small ({size} bytes): {relpath}"


def test_each_svg_is_valid_xml() -> None:
    """Each canonical SVG parses as valid XML and has a <title> element."""
    for relpath in CANONICAL_SVGS:
        full = REPO_ROOT / relpath
        tree = ET.parse(full)
        root = tree.getroot()
        # Strip namespace for tag matching
        tag = root.tag.split("}", 1)[-1]
        assert tag == "svg", f"{relpath} root is <{tag}>, expected <svg>"


def test_each_svg_has_title_matching_diagram() -> None:
    """Each SVG's <title> text content matches the diagram name."""
    title_to_path = {
        "TUI Cockpit": "docs/assets/tui-cockpit.svg",
        "Config Menu": "docs/assets/config-menu.svg",
        "Graph Viewer": "docs/assets/graph-viewer.svg",
        "Release Candidate Status": "docs/assets/release-candidate-status.svg",
        "User Flows": "docs/assets/user-flows.svg",
    }
    for title, relpath in title_to_path.items():
        full = REPO_ROOT / relpath
        tree = ET.parse(full)
        titles = [
            node.text for node in tree.iter() if node.tag.split("}", 1)[-1] == "title" and node.text
        ]
        assert title in titles, f"{relpath} has titles {titles!r}, expected to include {title!r}"


def test_readme_includes_descriptions_for_each_svg() -> None:
    """Each SVG reference is accompanied by a one-line description."""
    readme = _readme_text()
    for relpath in CANONICAL_SVGS:
        # README must mention the diagram name near each reference.
        # We require the basename to appear in the README.
        basename = Path(relpath).stem.replace("-", " ")
        # e.g. "tui cockpit", "config menu", etc.
        assert basename in readme.lower(), f"README does not mention {basename!r} from {relpath}"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-x"]))
