"""Skill registry scanner for discovering and indexing skills."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n",
    re.DOTALL | re.MULTILINE,
)
TRIGGER_RE = re.compile(r"Trigger:\s*(.+)", re.IGNORECASE)


@dataclass(frozen=True)
class SkillEntry:
    """A discovered skill entry."""

    name: str
    path: Path
    triggers: list[str]
    compact_rules: str
    source: str  # "user" or "project"


def _normalize_path(path: str) -> Path:
    """Expand user home and resolve to absolute path."""

    return Path(path).expanduser().resolve()


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Parse YAML-like frontmatter from SKILL.md content."""

    match = FRONTMATTER_RE.match(content)
    if not match:
        return {}

    raw = match.group(1)
    data: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[str] = []

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # List item continuation
        if stripped.startswith("-"):
            if current_key is not None:
                item = stripped.lstrip("-").strip().strip('"').strip("'")
                if item:
                    current_list.append(item)
            continue

        # Key: value
        if ":" in stripped:
            if current_key is not None and current_list:
                data[current_key] = current_list
                current_list = []

            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if value:
                data[key] = value
                current_key = None
            else:
                current_key = key
                current_list = []

    if current_key is not None and current_list:
        data[current_key] = current_list

    return data


def _extract_compact_rules(content: str, max_lines: int = 15) -> str:
    """Extract compact actionable rules from a SKILL.md body.

    Returns the first N non-empty, non-header lines after frontmatter
    that contain actionable content (rules, constraints, gotchas).
    """

    # Remove frontmatter
    body = FRONTMATTER_RE.sub("", content, count=1).strip()

    lines: list[str] = []
    for raw in body.splitlines():
        stripped = raw.strip()
        # Skip headers, empty lines, fluff
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("<") or stripped.startswith("!"):
            continue
        lowered = stripped.lower()
        if "example" in lowered or "purpose" in lowered or "fluff" in lowered:
            continue
        if len(stripped) < 10:
            continue
        lines.append(stripped)
        if len(lines) >= max_lines:
            break

    return "\n".join(lines)


def _extract_triggers(frontmatter: dict[str, Any]) -> list[str]:
    """Extract trigger keywords from frontmatter description or trigger field."""

    triggers: list[str] = []

    # Direct trigger field
    trigger = frontmatter.get("trigger")
    if trigger:
        if isinstance(trigger, list):
            triggers.extend(str(t).lower() for t in trigger)
        else:
            triggers.extend(str(trigger).lower().split(","))

    # Extract from description
    description = frontmatter.get("description", "")
    if description:
        desc_match = TRIGGER_RE.search(str(description))
        if desc_match:
            triggers.append(desc_match.group(1).lower().strip())

    # Deduplicate and clean
    cleaned = []
    for t in triggers:
        for word in t.split(","):
            word = word.strip().lower()
            if word and word not in cleaned:
                cleaned.append(word)

    return cleaned


def scan_skill_directory(
    directory: Path | str,
    source: str = "user",
) -> list[SkillEntry]:
    """Scan a directory tree for SKILL.md files and extract entries.

    Args:
        directory: Root directory to scan.
        source: Source label ("user" or "project").

    Returns:
        List of discovered skill entries.
    """

    root = _normalize_path(str(directory))
    if not root.exists():
        return []

    entries: list[SkillEntry] = []
    for path in root.rglob("SKILL.md"):
        content = path.read_text(encoding="utf-8")
        frontmatter = _parse_frontmatter(content)

        name = str(frontmatter.get("name", path.parent.name))
        triggers = _extract_triggers(frontmatter)
        compact = _extract_compact_rules(content)

        entries.append(
            SkillEntry(
                name=name,
                path=path,
                triggers=triggers,
                compact_rules=compact,
                source=source,
            )
        )

    return entries


def build_registry(
    user_dirs: list[str],
    project_dirs: list[str],
) -> list[SkillEntry]:
    """Build a deduplicated skill registry from user and project directories.

    Project-level skills take precedence over user-level skills with the same name.

    Args:
        user_dirs: User-level skill directories.
        project_dirs: Project-level skill directories.

    Returns:
        Deduplicated list of skill entries (project-level preferred).
    """

    seen: set[str] = set()
    registry: list[SkillEntry] = []

    # Scan user dirs first (lower priority)
    for user_dir in user_dirs:
        for entry in scan_skill_directory(user_dir, source="user"):
            if entry.name not in seen:
                seen.add(entry.name)
                registry.append(entry)

    # Scan project dirs (higher priority, overrides)
    for project_dir in project_dirs:
        for entry in scan_skill_directory(project_dir, source="project"):
            if entry.name in seen:
                # Replace with project-level version
                registry = [e for e in registry if e.name != entry.name]
            seen.add(entry.name)
            registry.append(entry)

    return registry


def render_registry_markdown(registry: list[SkillEntry]) -> str:
    """Render the registry as a Markdown document."""

    lines = ["# Skill Registry\n"]

    for entry in registry:
        lines.append(f"## {entry.name}")
        lines.append(f"- **Path**: `{entry.path}`")
        lines.append(f"- **Source**: {entry.source}")
        lines.append(f"- **Triggers**: {', '.join(entry.triggers) or 'N/A'}")
        lines.append("- **Compact Rules**:")
        for rule_line in entry.compact_rules.splitlines():
            lines.append(f"  - {rule_line}")
        lines.append("")

    return "\n".join(lines)
