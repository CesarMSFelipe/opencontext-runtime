"""Tests for scanner.is_ignored gitignore-style matching."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.config import DEFAULT_IGNORE_PATTERNS
from opencontext_core.indexing.scanner import ProjectScanner, is_ignored

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


# ── B5: robust venv ignore (non-standard venv dir names) ──────────────────────


def test_default_patterns_ignore_nonstandard_venv_names() -> None:
    # Regression (B5): audit/CI venvs with non-standard names were indexed because
    # the patterns only matched literal '.venv'/'venv'. A '*venv*' dir must now be
    # excluded, while the canonical '.venv'/'venv' stay excluded.
    patterns = list(DEFAULT_IGNORE_PATTERNS)
    assert is_ignored(_ROOT / "oc-audit-venv" / "x.py", _ROOT, patterns) is True
    assert is_ignored(_ROOT / ".ci-venv" / "x.py", _ROOT, patterns) is True
    assert is_ignored(_ROOT / ".venv" / "x.py", _ROOT, patterns) is True
    assert is_ignored(_ROOT / "venv" / "x.py", _ROOT, patterns) is True


def test_scan_excludes_venv_by_pyvenv_marker(tmp_path: Path) -> None:
    # A directory carrying the canonical 'pyvenv.cfg' marker is a virtualenv and
    # must be skipped wholesale regardless of its name (robust per-walk check).
    venv = tmp_path / "oc-audit-venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    (venv / "leaked.py").write_text("import this\n", encoding="utf-8")

    ci_venv = tmp_path / ".ci-venv"
    ci_venv.mkdir()
    (ci_venv / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    (ci_venv / "also_leaked.py").write_text("x = 1\n", encoding="utf-8")

    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("def main() -> None:\n    pass\n", encoding="utf-8")

    scanned = ProjectScanner().scan(tmp_path)
    paths = {f.relative_path for f in scanned}

    assert "src/app.py" in paths
    assert not any(p.startswith("oc-audit-venv/") for p in paths)
    assert not any(p.startswith(".ci-venv/") for p in paths)
