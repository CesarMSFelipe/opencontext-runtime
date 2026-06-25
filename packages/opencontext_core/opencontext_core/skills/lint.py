"""Skill explain + lint (Workstream K).

Skills drift into "prompt soup" — bloated bodies, vague over-broad triggers,
missing structure — when nothing inspects them. ``explain_skill`` gives a
structured summary; ``lint_skill`` flags the soup with typed findings so an
agent or CI can act on them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.skills.registry import (
    _extract_compact_rules,
    _extract_triggers,
    _parse_frontmatter,
)

Severity = Literal["error", "warning", "info"]

# Prompt-soup thresholds. NOTE: simple constants, tune if real skills outgrow them.
_MAX_BODY_LINES = 300
_MAX_DESCRIPTION_CHARS = 500
_MAX_TRIGGERS = 20


class SkillExplanation(BaseModel):
    """Structured summary of one skill file."""

    model_config = ConfigDict(extra="forbid")

    name: str
    path: str
    description: str = ""
    triggers: list[str] = Field(default_factory=list)
    sections: list[str] = Field(default_factory=list)
    body_lines: int = Field(default=0, ge=0)
    estimated_tokens: int = Field(default=0, ge=0)


class SkillLintFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: Severity
    message: str


class SkillLintReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    findings: list[SkillLintFinding] = Field(default_factory=list)

    def ok(self) -> bool:
        """True when there are no error-severity findings."""
        return not any(f.severity == "error" for f in self.findings)


def _resolve_skill_file(path: Path) -> Path:
    return path / "SKILL.md" if path.is_dir() else path


def _sections(content: str) -> list[str]:
    return [line[3:].strip() for line in content.splitlines() if line.startswith("## ")]


def explain_skill(path: Path | str) -> SkillExplanation:
    """Return a structured explanation of a skill file.

    Raises FileNotFoundError if the skill file does not exist (fail-closed —
    never fabricate an explanation for a missing skill).
    """
    skill_file = _resolve_skill_file(Path(path))
    if not skill_file.exists():
        raise FileNotFoundError(f"Skill file not found: {skill_file}")

    content = skill_file.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(content)
    body_lines = content.count("\n") + 1
    # NOTE: char/4 token estimate — good enough to flag bloat, not billing.
    estimated_tokens = len(content) // 4

    return SkillExplanation(
        name=str(frontmatter.get("name", skill_file.parent.name)),
        path=str(skill_file),
        description=str(frontmatter.get("description", "")),
        triggers=_extract_triggers(frontmatter),
        sections=_sections(content),
        body_lines=body_lines,
        estimated_tokens=estimated_tokens,
    )


def lint_skill(path: Path | str) -> SkillLintReport:
    """Lint a skill file for prompt-soup smells. Fail-closed on a missing file."""
    skill_file = _resolve_skill_file(Path(path))
    if not skill_file.exists():
        return SkillLintReport(
            path=str(skill_file),
            findings=[
                SkillLintFinding(
                    code="missing_file",
                    severity="error",
                    message=f"Skill file not found: {skill_file}",
                )
            ],
        )

    content = skill_file.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(content)
    triggers = _extract_triggers(frontmatter)
    description = str(frontmatter.get("description", ""))
    body_lines = content.count("\n") + 1
    compact = _extract_compact_rules(content)

    findings: list[SkillLintFinding] = []

    if not frontmatter.get("name"):
        findings.append(
            SkillLintFinding(code="missing_name", severity="error", message="Skill has no name.")
        )
    if not description:
        findings.append(
            SkillLintFinding(
                code="missing_description",
                severity="error",
                message="Skill has no description — it cannot be matched or explained.",
            )
        )
    elif len(description) > _MAX_DESCRIPTION_CHARS:
        findings.append(
            SkillLintFinding(
                code="description_too_long",
                severity="warning",
                message=f"Description is {len(description)} chars "
                f"(> {_MAX_DESCRIPTION_CHARS}); tighten it.",
            )
        )
    if not triggers:
        findings.append(
            SkillLintFinding(
                code="no_triggers",
                severity="warning",
                message="Skill declares no triggers — it will never auto-activate.",
            )
        )
    elif len(triggers) > _MAX_TRIGGERS:
        findings.append(
            SkillLintFinding(
                code="too_many_triggers",
                severity="warning",
                message=f"{len(triggers)} triggers (> {_MAX_TRIGGERS}) — likely over-broad, "
                "will fire on unrelated tasks.",
            )
        )
    if body_lines > _MAX_BODY_LINES:
        findings.append(
            SkillLintFinding(
                code="body_too_long",
                severity="warning",
                message=f"Body is {body_lines} lines (> {_MAX_BODY_LINES}) — prompt-soup risk; "
                "split or compress.",
            )
        )
    if not compact:
        findings.append(
            SkillLintFinding(
                code="no_actionable_content",
                severity="warning",
                message="No actionable rules detected — the skill may be all prose, no guidance.",
            )
        )

    return SkillLintReport(path=str(skill_file), findings=findings)
