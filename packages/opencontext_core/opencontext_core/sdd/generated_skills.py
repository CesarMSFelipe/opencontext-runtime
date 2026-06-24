"""Generated per-phase SDD skill stubs (CAP6 — opt-in, project namespace).

Skill stubs are written to ``.opencontext/skills/oc-sdd-{phase}-{change}.md``.
They are NEVER written to ``~/.claude/skills/`` to avoid shadowing
user-maintained global skills. Generation is opt-in and never overwrites
an existing user-maintained stub.
"""

from __future__ import annotations

from pathlib import Path

_SKILL_DIR = Path(".opencontext") / "skills"
_SKILL_PREFIX = "oc-sdd"
_SKILL_SUFFIX = ".md"
_FRONTMATTER = (
    "---\n"
    "name: oc-sdd-{phase}-{change}\n"
    "description: Generated per-phase SDD stub for {change} ({phase}).\n"
    "generated: true\n"
    "---\n\n"
)


def write_skill_stub(
    project_root: Path,
    change_id: str,
    phase: str,
    body: str,
    *,
    enabled: bool = False,
) -> Path | None:
    """Write a skill stub when *enabled* is True. Default off → no-op.

    Returns the stub path on success; None when disabled.
    NEVER writes under ``~/.claude/skills/`` — fails closed if a leak
    would occur.
    """
    if not enabled:
        return None
    home = Path.home()
    skills_dir = project_root / _SKILL_DIR
    try:
        skills_dir.resolve().relative_to(home.resolve() / ".claude")
    except ValueError:
        pass
    else:
        raise RuntimeError("write_skill_stub resolved under ~/.claude/skills — refusing to write")
    skills_dir.mkdir(parents=True, exist_ok=True)
    stub_path = skills_dir / f"{_SKILL_PREFIX}-{phase}-{change_id}{_SKILL_SUFFIX}"
    if stub_path.exists():
        return stub_path
    content = _FRONTMATTER.format(phase=phase, change=change_id) + body
    stub_path.write_text(content)
    return stub_path


__all__ = ["write_skill_stub"]
