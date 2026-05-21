"""Compact rules generator for skill registry entries."""

from __future__ import annotations

from opencontext_core.skills.registry import SkillEntry


def generate_compact_rules(skills: list[SkillEntry], max_per_skill: int = 15) -> str:
    """Generate a single compact rules block from multiple skill entries.

    Each skill contributes up to max_per_skill lines of actionable rules.
    Rules are formatted as markdown with skill name headers.

    Args:
        skills: List of resolved skill entries.
        max_per_skill: Maximum lines per skill (default 15).

    Returns:
        Markdown-formatted compact rules block.
    """

    lines: list[str] = []

    for skill in skills:
        if not skill.compact_rules.strip():
            continue

        lines.append(f"### {skill.name}")
        rules = skill.compact_rules.splitlines()
        for rule in rules[:max_per_skill]:
            if rule.strip():
                lines.append(rule)
        lines.append("")

    return "\n".join(lines)
