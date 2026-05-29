"""Skill CLI commands: create and validate skills."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from opencontext_core.dx.console_styles import console
from opencontext_core.skills.scaffolder import scaffold_skill

FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n",
    re.DOTALL | re.MULTILINE,
)


def add_skill_parser(subparsers: Any) -> None:
    """Add skill command parsers."""

    skill_parser = subparsers.add_parser("skill", help="Manage AI skills.")
    skill_sub = skill_parser.add_subparsers(dest="skill_command", required=True)

    # skill create
    create_parser = skill_sub.add_parser("create", help="Create a new skill.")
    create_parser.add_argument("name", help="Skill name.")
    create_parser.add_argument("--output-dir", default=".", help="Output directory.")
    create_parser.add_argument("--description", default=None, help="Skill description.")
    create_parser.add_argument("--triggers", default=None, help="Comma-separated triggers.")
    create_parser.add_argument("--author", default=None, help="Skill author.")
    create_parser.add_argument("--force", action="store_true", help="Overwrite existing.")

    # skill validate
    validate_parser = skill_sub.add_parser("validate", help="Validate a SKILL.md file.")
    validate_parser.add_argument("path", help="Path to SKILL.md or skill directory.")


def handle_skill(args: Any) -> None:
    """Handle skill commands."""

    command = args.skill_command

    if command == "create":
        _handle_create(args)
    elif command == "validate":
        _handle_validate(args)


def _handle_create(args: Any) -> None:
    name = args.name
    output_dir = args.output_dir

    # Interactive prompts for missing flags
    description = args.description
    if description is None:
        description = console.ask("Skill description")

    triggers = args.triggers
    if triggers is None:
        triggers = console.ask("Comma-separated trigger phrases")

    author = args.author
    if author is None:
        author = console.ask("Author name")

    try:
        result = scaffold_skill(
            name=name,
            output_dir=output_dir,
            description=description,
            triggers=triggers,
            author=author,
            force=args.force,
        )
        console.print(f"[green]Created skill at[/] {result}")
    except FileExistsError as exc:
        console.error(str(exc))
        raise SystemExit(1) from exc


def _handle_validate(args: Any) -> None:
    path = Path(args.path)

    if path.is_dir():
        skill_file = path / "SKILL.md"
    else:
        skill_file = path

    if not skill_file.exists():
        console.error(f"File not found: {skill_file}")
        raise SystemExit(1)

    content = skill_file.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(content)

    checks = [
        ("name", "name" in frontmatter and bool(frontmatter["name"])),
        ("description", "description" in frontmatter and bool(frontmatter["description"])),
        ("triggers", "triggers" in frontmatter and bool(frontmatter["triggers"])),
        ("author", "author" in frontmatter and bool(frontmatter["author"])),
        ("version", "version" in frontmatter and bool(frontmatter["version"])),
    ]

    # Body section checks
    _body = frontmatter.get("_body", content)
    has_overview = "## Overview" in content
    has_implementation = "## Implementation" in content
    has_common_mistakes = "## Common Mistakes" in content
    checks.append(("section: Overview", has_overview))
    checks.append(("section: Implementation", has_implementation))
    checks.append(("section: Common Mistakes", has_common_mistakes))

    all_pass = True
    for label, passed in checks:
        if passed:
            console.print(f"  [green]PASS[/]  {label}")
        else:
            console.print(f"  [red]FAIL[/]  {label}")
            all_pass = False

    if all_pass:
        console.print(f"[green]All checks passed for[/] {skill_file}")
        raise SystemExit(0)
    else:
        console.print(f"[red]Some checks failed for[/] {skill_file}")
        raise SystemExit(1)


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Parse YAML-like frontmatter from SKILL.md content."""

    match = FRONTMATTER_RE.match(content)
    if not match:
        return {"_body": content}

    raw = match.group(1)
    data: dict[str, Any] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            data[key.strip()] = value.strip()

    body_start = match.end()
    data["_body"] = content[body_start:].strip()
    return data
