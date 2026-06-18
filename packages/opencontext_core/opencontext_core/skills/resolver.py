"""Skill resolver for matching skills by code context and task context."""

from __future__ import annotations

import fnmatch

from opencontext_core.skills.registry import SkillEntry


def resolve_skills(
    registry: list[SkillEntry],
    file_patterns: list[str],
    task_type: str,
    max_matches: int = 5,
) -> list[SkillEntry]:
    """Resolve matching skills by code context and task context.

    Matches on two dimensions:
    1. Code context: file patterns the sub-agent will touch
    2. Task context: actions the sub-agent will perform

    Args:
        registry: Full skill registry.
        file_patterns: List of file paths/patterns the sub-agent will touch.
        task_type: Description of the task (e.g., "review PR", "write tests").
        max_matches: Maximum number of skills to return (default 5).

    Returns:
        List of matching skills, sorted by relevance, capped at max_matches.
    """

    code_matches: list[tuple[int, SkillEntry]] = []
    task_matches: list[tuple[int, SkillEntry]] = []

    for skill in registry:
        # Code context match: file patterns vs skill path or triggers
        code_score = _score_code_context(skill, file_patterns)
        if code_score > 0:
            code_matches.append((code_score, skill))

        # Task context match: task type vs skill triggers
        task_score = _score_task_context(skill, task_type)
        if task_score > 0:
            task_matches.append((task_score, skill))

    # Combine scores: code context has higher priority than task context
    combined: dict[str, tuple[int, SkillEntry]] = {}

    for score, skill in code_matches:
        combined[skill.name] = (score * 2, skill)

    for score, skill in task_matches:
        if skill.name in combined:
            existing_score, _ = combined[skill.name]
            combined[skill.name] = (existing_score + score, skill)
        else:
            combined[skill.name] = (score, skill)

    sorted_skills = sorted(combined.values(), key=lambda x: -x[0])

    return [skill for _, skill in sorted_skills[:max_matches]]


def _score_code_context(skill: SkillEntry, file_patterns: list[str]) -> int:
    """Score how well a skill matches the file patterns.

    Returns a positive integer score, or 0 if no match.
    """

    score = 0
    skill_path = str(skill.path).lower()

    for pattern in file_patterns:
        pattern_lower = pattern.lower()

        # Direct path match
        if pattern_lower in skill_path:
            score += 3
            continue

        # Extension match
        if pattern_lower.startswith("*.") and skill_path.endswith(pattern_lower[1:]):
            score += 2
            continue

        # Glob match
        if fnmatch.fnmatch(skill_path, pattern_lower):
            score += 2
            continue

        # Directory match
        if "/" in pattern_lower:
            dir_part = pattern_lower.split("/")[0]
            if dir_part in skill_path:
                score += 1

    return score


def _score_task_context(skill: SkillEntry, task_type: str) -> int:
    """Score how well a skill matches the task type.

    Returns a positive integer score, or 0 if no match.
    """

    task_lower = task_type.lower()
    score = 0

    for trigger in skill.triggers:
        trigger_lower = trigger.lower()

        # Exact match
        if trigger_lower == task_lower:
            score += 3
            continue

        # Substring match
        if trigger_lower in task_lower or task_lower in trigger_lower:
            score += 2
            continue

        # Word-level match
        task_words = set(task_lower.split())
        trigger_words = set(trigger_lower.split())
        overlap = task_words & trigger_words
        if overlap:
            score += len(overlap)

    return score
