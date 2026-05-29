"""Skill scaffolder: create skill directory with SKILL.md and README.md."""

from __future__ import annotations

from pathlib import Path

SKILL_MD_TEMPLATE = """---
name: {name}
description: {description}
triggers: {triggers}
author: {author}
version: {version}
---

# {name}

## Overview

<!-- Brief description of what this skill does and when to use it.
     Explain the problem it solves and the value it provides. -->

{description}

## Implementation

<!-- Step-by-step instructions for the AI agent.
     Include concrete examples, code snippets, and expected patterns.
     Cover edge cases and common pitfalls. -->

### Steps

1. <!-- Step one -->
2. <!-- Step two -->
3. <!-- Step three -->

### Example

```python
# Example usage
```

## Common Mistakes

<!-- List frequent errors or anti-patterns the AI agent should avoid. -->

- <!-- Mistake 1: description and correction -->
- <!-- Mistake 2: description and correction -->
"""

README_TEMPLATE = """# {name} Skill

{description}

## Usage

This skill is triggered by: {triggers}

## Author

{author}
"""


def scaffold_skill(
    name: str,
    output_dir: str = ".",
    description: str = "",
    triggers: str = "",
    author: str = "",
    force: bool = False,
) -> str:
    """Create a skill directory with SKILL.md and README.md.

    Args:
        name: Skill name (used as directory and in frontmatter).
        output_dir: Parent directory for the skill folder.
        description: Short description of the skill.
        triggers: Comma-separated trigger phrases.
        author: Skill author name.
        force: Overwrite existing directory if True.

    Returns:
        Path to the created skill directory as a string.

    Raises:
        FileExistsError: If the directory exists and force is False.
    """

    skill_dir = Path(output_dir) / name

    if skill_dir.exists():
        if not force:
            raise FileExistsError(
                f"Skill directory already exists: {skill_dir}. Use --force to overwrite."
            )

    skill_dir.mkdir(parents=True, exist_ok=True)

    # Write SKILL.md
    skill_path = skill_dir / "SKILL.md"
    skill_content = SKILL_MD_TEMPLATE.format(
        name=name,
        description=description or "No description provided.",
        triggers=triggers or "Not specified",
        author=author or "Unknown",
        version="0.1.0",
    )
    skill_path.write_text(skill_content, encoding="utf-8")

    # Write README.md
    readme_path = skill_dir / "README.md"
    readme_content = README_TEMPLATE.format(
        name=name,
        description=description or "No description provided.",
        triggers=triggers or "Not specified",
        author=author or "Unknown",
    )
    readme_path.write_text(readme_content, encoding="utf-8")

    return str(skill_dir)
