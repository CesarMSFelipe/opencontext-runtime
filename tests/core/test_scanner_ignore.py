"""Tests for scanner.is_ignored gitignore-style matching."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.indexing.scanner import is_ignored

_ROOT = Path("/proj")


def test_unanchored_pattern_matches_at_any_level() -> None:
    assert is_ignored(_ROOT / "src" / "build" / "x.py", _ROOT, ["build"]) is True
    assert is_ignored(_ROOT / "build" / "x.py", _ROOT, ["build"]) is True


def test_unanchored_pattern_is_component_exact_not_substring() -> None:
    # 'build' must NOT match 'rebuild/' or 'mybuild.py'.
    assert is_ignored(_ROOT / "rebuild" / "x.py", _ROOT, ["build"]) is False
    assert is_ignored(_ROOT / "mybuild.py", _ROOT, ["build"]) is False


def test_leading_slash_anchors_to_root() -> None:
    # Regression: '/build' must ignore top-level build/ but not nested src/build/.
    assert is_ignored(_ROOT / "build" / "x.py", _ROOT, ["/build"]) is True
    assert is_ignored(_ROOT / "src" / "build" / "x.py", _ROOT, ["/build"]) is False


def test_glob_pattern_matches_basename() -> None:
    assert is_ignored(_ROOT / "src" / "a.log", _ROOT, ["*.log"]) is True
    assert is_ignored(_ROOT / "src" / "a.py", _ROOT, ["*.log"]) is False
