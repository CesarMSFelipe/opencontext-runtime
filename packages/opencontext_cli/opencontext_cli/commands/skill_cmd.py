"""Skill CLI commands: create and validate skills."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from opencontext_cli.output import eprint
from opencontext_core import prompts
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

    list_parser = skill_sub.add_parser(
        "list", help="List available skills from registry and agent skill dirs."
    )
    list_parser.add_argument("--root", default=".", help="Project root.")
    list_parser.add_argument("--json", action="store_true", help="JSON output.")

    create_parser = skill_sub.add_parser("create", help="Create a new skill.")
    create_parser.add_argument("name", help="Skill name.")
    create_parser.add_argument("--output-dir", default=".", help="Output directory.")
    create_parser.add_argument("--description", default=None, help="Skill description.")
    create_parser.add_argument("--triggers", default=None, help="Comma-separated triggers.")
    create_parser.add_argument("--author", default=None, help="Skill author.")
    create_parser.add_argument("--force", action="store_true", help="Overwrite existing.")

    validate_parser = skill_sub.add_parser("validate", help="Validate a SKILL.md file.")
    validate_parser.add_argument("path", help="Path to SKILL.md or skill directory.")

    explain_parser = skill_sub.add_parser(
        "explain", help="Explain a skill: name, triggers, sections, size."
    )
    explain_parser.add_argument("path", help="Path to SKILL.md or skill directory.")
    explain_parser.add_argument("--json", action="store_true", help="JSON output.")

    lint_parser = skill_sub.add_parser(
        "lint", help="Lint a skill for prompt-soup smells (bloat, vague triggers)."
    )
    lint_parser.add_argument("path", help="Path to SKILL.md or skill directory.")
    lint_parser.add_argument("--json", action="store_true", help="JSON output.")

    audit_parser = skill_sub.add_parser(
        "audit", help="Audit skill YAML files for quality/security issues."
    )
    audit_parser.add_argument(
        "--root", default=".", help="Root directory containing skill YAML files."
    )
    audit_parser.add_argument("--json", action="store_true", help="JSON output.")

    catalog_parser = skill_sub.add_parser("catalog", help="Manage the skill catalog.")
    catalog_subs = catalog_parser.add_subparsers(dest="catalog_command", required=True)
    cat_gen = catalog_subs.add_parser("generate", help="Generate or check the skill catalog.")
    cat_gen.add_argument("--root", default=".", help="Root directory containing skill YAML files.")
    cat_gen.add_argument(
        "--check",
        action="store_true",
        help="Dry-run check: exit 1 when catalog is drifted, 0 when in sync.",
    )
    cat_gen.add_argument("--json", action="store_true", help="JSON output.")


def handle_skill(args: Any) -> None:
    """Handle skill commands."""

    command = args.skill_command

    if command == "list":
        _handle_list(args)
    elif command == "create":
        _handle_create(args)
    elif command == "validate":
        _handle_validate(args)
    elif command == "explain":
        _handle_explain(args)
    elif command == "lint":
        _handle_lint(args)
    elif command == "audit":
        _handle_audit(args)
    elif command == "catalog":
        _handle_catalog(args)


def _handle_list(args: Any) -> None:
    import json as _json
    from pathlib import Path as _Path

    root = _Path(getattr(args, "root", ".")).resolve()
    json_out = getattr(args, "json", False)

    skills: list[dict[str, str]] = []

    # Parse project skill registry (.opencontext/skill-registry.md)
    registry_path = root / ".opencontext" / "skill-registry.md"
    if registry_path.exists():
        content = registry_path.read_text(encoding="utf-8")
        current: dict[str, str] = {}
        for line in content.splitlines():
            if line.startswith("## "):
                if current:
                    skills.append(current)
                current = {"name": line[3:].strip(), "source": "registry"}
            elif line.startswith("**Description:**") and current:
                current["description"] = line.split("**Description:**", 1)[1].strip()
            elif line.startswith("**Path:**") and current:
                current["path"] = line.split("**Path:**", 1)[1].strip().strip("`")
        if current:
            skills.append(current)

    # Also scan .claude/skills/ for agent-local skills
    agent_skills_dir = _Path.home() / ".claude" / "skills"
    if agent_skills_dir.exists():
        for skill_file in sorted(agent_skills_dir.glob("*.md")):
            name = skill_file.stem
            if not any(s["name"] == name for s in skills):
                skills.append(
                    {
                        "name": name,
                        "source": "agent-local",
                        "path": str(skill_file),
                        "description": "",
                    }
                )

    if json_out:
        print(_json.dumps(skills, indent=2))
        return

    console.header(f"Skills ({len(skills)})")
    if not skills:
        console.info("No skills yet.")
        console.dim("Run 'opencontext skill-registry refresh' to scan.")
        return

    rows = [
        [s.get("name", "?"), s.get("source", "?"), s.get("description", "")[:60]] for s in skills
    ]
    console.table("Skills", ["Name", "Source", "Description"], rows)


def _handle_create(args: Any) -> None:
    name = args.name
    output_dir = args.output_dir

    description = args.description
    if description is None:
        description = prompts.text("Skill description")

    triggers = args.triggers
    if triggers is None:
        triggers = prompts.text("Comma-separated trigger phrases")

    author = args.author
    if author is None:
        author = prompts.text("Author name")

    console.header("Create Skill")
    try:
        result = scaffold_skill(
            name=name,
            output_dir=output_dir,
            description=description,
            triggers=triggers,
            author=author,
            force=args.force,
        )
        console.success(f"Created skill at {result}")
    except FileExistsError as exc:
        eprint(str(exc))
        raise SystemExit(1) from exc


def _handle_validate(args: Any) -> None:
    path = Path(args.path)

    if path.is_dir():
        skill_file = path / "SKILL.md"
    else:
        skill_file = path

    if not skill_file.exists():
        eprint(f"File not found: {skill_file}")
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

    _body = frontmatter.get("_body", content)
    has_overview = "## Overview" in content
    has_implementation = "## Implementation" in content
    has_common_mistakes = "## Common Mistakes" in content
    checks.append(("section: Overview", has_overview))
    checks.append(("section: Implementation", has_implementation))
    checks.append(("section: Common Mistakes", has_common_mistakes))

    console.header("Validate Skill")
    all_pass = all(passed for _, passed in checks)
    console.table(
        str(skill_file),
        ["Check", "Result"],
        [[label, "✓ pass" if passed else "✗ fail"] for label, passed in checks],
    )

    if all_pass:
        console.success(f"All checks passed for {skill_file}")
        raise SystemExit(0)
    else:
        eprint(f"Some checks failed for {skill_file}")
        raise SystemExit(1)


def _handle_explain(args: Any) -> None:
    import json as _json

    from opencontext_core.skills.lint import explain_skill

    try:
        explanation = explain_skill(args.path)
    except FileNotFoundError as exc:
        eprint(str(exc))
        raise SystemExit(1) from exc

    if getattr(args, "json", False):
        print(_json.dumps(explanation.model_dump(), indent=2))
        return

    console.header(f"Skill: {explanation.name}")
    console.print(f"Path: {explanation.path}")
    console.print(f"Description: {explanation.description or '—'}")
    console.print(f"Triggers: {', '.join(explanation.triggers) or '—'}")
    console.print(f"Sections: {', '.join(explanation.sections) or '—'}")
    console.print(f"Body lines: {explanation.body_lines}")
    console.print(f"Estimated tokens: {explanation.estimated_tokens}")


def _handle_lint(args: Any) -> None:
    import json as _json

    from opencontext_core.skills.lint import lint_skill

    report = lint_skill(args.path)

    if getattr(args, "json", False):
        print(_json.dumps(report.model_dump(), indent=2))
        raise SystemExit(0 if report.ok() else 1)

    console.header("Lint Skill")
    if not report.findings:
        console.success(f"No issues — {report.path}")
        raise SystemExit(0)

    _labels = {"error": "✗ error", "warning": "⚠ warning", "info": "i info"}
    console.table(
        str(report.path),
        ["Severity", "Code", "Message"],
        [[_labels.get(f.severity, f.severity), f.code, f.message] for f in report.findings],
    )
    raise SystemExit(0 if report.ok() else 1)


def _handle_audit(args: Any) -> None:
    import json as _json
    from pathlib import Path as _Path

    from opencontext_core.skills.v2.audit import SkillAudit

    root = _Path(getattr(args, "root", ".")).resolve()
    report = SkillAudit().run(root)

    if getattr(args, "json", False):
        print(_json.dumps([f.__dict__ for f in report.findings], indent=2))
    else:
        if not report.findings:
            console.success(f"No issues found in {root}")
        else:
            for finding in report.findings:
                console.print(f"[{finding.severity}] {finding.code}: {finding.message}")

    if report.errors:
        raise SystemExit(1)


def _handle_catalog(args: Any) -> None:
    catalog_cmd = getattr(args, "catalog_command", None)
    if catalog_cmd == "generate":
        _handle_catalog_generate(args)
    else:
        eprint("Usage: opencontext skill catalog generate [--check]")
        raise SystemExit(1)


def _handle_catalog_generate(args: Any) -> None:
    import json as _json
    from pathlib import Path as _Path

    from opencontext_core.skills.v2.catalog import dry_run_update, generate_catalog

    root = _Path(getattr(args, "root", ".")).resolve()
    check = getattr(args, "check", False)

    if check:
        report = dry_run_update(root)
        if getattr(args, "json", False):
            print(
                _json.dumps(
                    {
                        "drifted": report.drifted,
                        "current_count": len(report.current),
                    },
                    indent=2,
                )
            )
        else:
            if report.drifted:
                eprint(
                    f"Catalog is out of date with {root}. "
                    "Run 'opencontext skill catalog generate' to update."
                )
            else:
                console.success("Catalog is up to date.")
        if report.drifted:
            raise SystemExit(1)
    else:
        catalog = generate_catalog(root)
        cat_path = root / "catalog.json"
        cat_path.write_text(catalog.to_json(), encoding="utf-8")
        console.success(f"Catalog written to {cat_path}")


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
