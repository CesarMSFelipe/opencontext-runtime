"""Tests for skill explain + lint (Workstream K)."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.skills.lint import (
    SkillExplanation,
    SkillLintReport,
    explain_skill,
    lint_skill,
)

_GOOD_SKILL = """---
name: my-skill
description: Does a focused thing. Trigger: refactor, rename
author: me
version: 1.0.0
---

## Overview
This skill renames symbols safely across the codebase using the graph.

## Implementation
Always check impact before renaming. Run tests after each rename step.

## Common Mistakes
Do not rename without checking inbound references first.
"""


def _write(tmp_path: Path, content: str, name: str = "SKILL.md") -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ── explain ───────────────────────────────────────────────────────────────────


def test_explain_returns_structured(tmp_path: Path) -> None:
    p = _write(tmp_path, _GOOD_SKILL)
    ex = explain_skill(p)
    assert isinstance(ex, SkillExplanation)
    assert ex.name == "my-skill"
    assert "refactor" in ex.triggers or "rename" in ex.triggers
    assert "Overview" in ex.sections
    assert ex.body_lines > 0
    assert ex.estimated_tokens > 0


def test_explain_accepts_directory(tmp_path: Path) -> None:
    _write(tmp_path, _GOOD_SKILL)
    ex = explain_skill(tmp_path)
    assert ex.name == "my-skill"


def test_explain_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        explain_skill(tmp_path / "nope.md")


# ── lint ──────────────────────────────────────────────────────────────────────


def test_lint_good_skill_ok(tmp_path: Path) -> None:
    p = _write(tmp_path, _GOOD_SKILL)
    report = lint_skill(p)
    assert isinstance(report, SkillLintReport)
    assert report.ok() is True


def test_lint_missing_file_is_error(tmp_path: Path) -> None:
    report = lint_skill(tmp_path / "nope.md")
    assert report.ok() is False
    assert any(f.code == "missing_file" for f in report.findings)


def test_lint_missing_description_is_error(tmp_path: Path) -> None:
    p = _write(tmp_path, "---\nname: x\n---\n\n## Overview\nstuff here that is long enough\n")
    report = lint_skill(p)
    assert report.ok() is False
    assert any(f.code == "missing_description" for f in report.findings)


def test_lint_no_triggers_is_warning(tmp_path: Path) -> None:
    p = _write(
        tmp_path, "---\nname: x\ndescription: a thing with no triggers\n---\n\nbody line here\n"
    )
    report = lint_skill(p)
    codes = {f.code for f in report.findings}
    assert "no_triggers" in codes
    # warning only → still ok()
    assert report.ok() is True


def test_lint_body_too_long_is_warning(tmp_path: Path) -> None:
    body = "\n".join(f"line of content number {i}" for i in range(400))
    p = _write(tmp_path, f"---\nname: x\ndescription: d. Trigger: foo\n---\n\n{body}\n")
    report = lint_skill(p)
    assert any(f.code == "body_too_long" for f in report.findings)


def test_lint_too_many_triggers_is_warning(tmp_path: Path) -> None:
    triggers = ", ".join(f"kw{i}" for i in range(30))
    p = _write(tmp_path, f"---\nname: x\ndescription: d. Trigger: {triggers}\n---\n\nbody line\n")
    report = lint_skill(p)
    assert any(f.code == "too_many_triggers" for f in report.findings)


def test_lint_report_forbids_extra() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SkillLintReport(path="p", findings=[], bogus=1)
