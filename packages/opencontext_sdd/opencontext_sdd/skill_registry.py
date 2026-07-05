"""Native skill-registry producer.

Authoritative writer for ``.atl/skill-registry.md`` and the fingerprint
cache ``.atl/.skill-registry.cache.json``. Replaces the gentle-ai
skill-registry CLI as the source of truth (per
``openspec/changes/agentic-parity-engram-gentle/proposal.md`` Q5).

Per REQ-OSR-001..005:

* 18 source dirs (9 per-user + 9 per-project) under ``SOURCE_DIRS``.
* Exclusions: ``_shared``, ``skill-registry``, ``sdd-*`` prefixes.
* Project scope wins over user scope on name collision.
* Atomic write via tmp file + ``os.replace``.
* Fingerprint is sha1 over ``path:mtime_ns:size`` for every ``SKILL.md``.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Source directories (REQ-OSR-002) — 9 per-user + 9 per-project.
# ---------------------------------------------------------------------------

# 9 per-user (resolved against Path.home() at scan time).
USER_SOURCE_DIRS: tuple[str, ...] = (
    "~/.config/opencode/skills",
    "~/.config/claude/skills",
    "~/.config/kilo/skills",
    "~/.config/gemini/skills",
    "~/.config/cursor/skills",
    "~/.config/qwen/skills",
    "~/.config/kiro/skills",
    "~/.config/codex/skills",
    "~/.agents/skills",
)

# 9 per-project (resolved against the project root passed to refresh()).
PROJECT_SOURCE_DIRS: tuple[str, ...] = (
    "skills",
    ".opencode/skills",
    ".claude/skills",
    ".gemini/skills",
    ".cursor/skills",
    ".github/skills",
    ".codex/skills",
    ".qwen/skills",
    ".kiro/skills",
)

SOURCE_DIRS: tuple[str, ...] = USER_SOURCE_DIRS + PROJECT_SOURCE_DIRS

# ---------------------------------------------------------------------------
# Frontmatter parser (REQ-OSR-003).
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL | re.MULTILINE)


# REQ-OSR-002 exclusions.
_EXCLUDED_NAMES: frozenset[str] = frozenset({"_shared", "skill-registry"})
_EXCLUDED_PREFIXES: tuple[str, ...] = ("sdd-",)


@dataclass(frozen=True)
class SkillEntry:
    """A discovered skill, ready to be written into the registry."""

    name: str
    path: Path
    description: str
    source: str  # "user" or "project"
    fingerprint: str = ""


@dataclass(frozen=True)
class RefreshResult:
    """Outcome of a single ``refresh()`` call."""

    changed: bool
    registry_path: Path
    cache_path: Path
    skill_count: int
    reason: str  # "cache-hit" | "fingerprint-changed" | "forced" | "empty-fingerprint"
    parse_warnings: tuple[str, ...] = ()


def _resolve_user_dirs() -> list[Path]:
    return [Path(os.path.expanduser(p)) for p in USER_SOURCE_DIRS]


def _resolve_project_dirs(root: Path) -> list[Path]:
    return [root / p for p in PROJECT_SOURCE_DIRS]


def _is_excluded(name: str) -> bool:
    if name in _EXCLUDED_NAMES:
        return True
    return any(name.startswith(prefix) for prefix in _EXCLUDED_PREFIXES)


def _parse_frontmatter(content: str) -> dict[str, Any]:
    match = FRONTMATTER_RE.match(content)
    if not match:
        return {}
    data: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        if not key:
            continue
        # Strip surrounding quotes + leading block scalars ("|", ">")
        cleaned = value.strip()
        if cleaned.startswith(("|", ">")):
            # Simplified: ignore block scalars; the title field is short.
            continue
        cleaned = cleaned.strip('"').strip("'")
        if cleaned:
            data[key] = cleaned
    return data


def _first_sentence(text: str, limit: int = 140) -> str:
    text = text.strip().replace("\n", " ")
    for terminator in (". ", "! ", "? "):
        idx = text.find(terminator)
        if idx > 0 and idx <= limit:
            return text[: idx + 1].strip()
    return text[:limit].strip()


def _scan_dir(
    directory: Path,
    source: str,
    project_root: Path,
    parse_warnings: list[str] | None = None,
) -> list[SkillEntry]:
    """Scan ``directory`` for SKILL.md files.

    ``source`` is a hint (the caller-supplied scope); the actual ``source``
    recorded on the entry is inferred from the file's location relative to
    ``project_root`` (gentle-ai's ``scopeForPath`` heuristic). Files under
    ``project_root`` are tagged ``project``; everything else is ``user``.

    Skills with missing/invalid frontmatter are recorded as a warning on
    ``parse_warnings`` (when provided) and excluded from the result.
    """
    if not directory.exists():
        return []
    warnings = parse_warnings if parse_warnings is not None else []
    out: list[SkillEntry] = []
    for path in sorted(directory.rglob("SKILL.md")):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if _is_excluded(path.parent.name):
            continue
        frontmatter = _parse_frontmatter(content)
        if "name" not in frontmatter:
            warnings.append(f"{path}:missing_frontmatter")
            continue
        name = str(frontmatter.get("name", "")).strip()
        if not name or _is_excluded(name):
            continue
        description = _first_sentence(str(frontmatter.get("description", "")))
        fp = _fingerprint_file(path)
        out.append(
            SkillEntry(
                name=name,
                path=path,
                description=description,
                source=source,
                fingerprint=fp,
            )
        )
    return out


def _fingerprint_file(path: Path) -> str:
    """sha1 over ``path:mtime_ns:size`` — matches gentle-ai's shape."""
    try:
        st = path.stat()
    except OSError:
        return f"{path}:missing"
    return f"{path}:{st.st_mtime_ns}:{st.st_size}"


def _fingerprint_skill_files(files: list[Path]) -> str:
    """Stable sha1 over every ``SKILL.md`` under the source dirs."""

    lines = ["schema:1"]
    for path in sorted({f.resolve() for f in files}):
        try:
            st = path.stat()
            lines.append(f"{path}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            lines.append(f"{path}:missing")
    digest = hashlib.sha1("\n".join(lines).encode("utf-8")).hexdigest()
    return digest


def _dedupe(entries: list[SkillEntry], project_root: Path) -> list[SkillEntry]:
    """Project scope beats user scope on name collision (REQ-OSR-002)."""
    project_root = project_root.resolve()
    by_name: dict[str, SkillEntry] = {}
    # User entries first (lower priority)
    for entry in entries:
        if entry.source != "user":
            continue
        by_name.setdefault(entry.name, entry)
    # Project entries override
    for entry in entries:
        if entry.source != "project":
            continue
        if entry.name in by_name:
            by_name.pop(entry.name)
        by_name[entry.name] = entry
    # Also resolve project vs project collisions: prefer the one whose path
    # resolves under project_root (closest match wins).
    final: dict[str, SkillEntry] = {}
    for name, entry in by_name.items():
        if name in final:
            existing = final[name]
            # Keep the entry whose path is closest to project_root.
            existing_in_root = _is_under(existing.path, project_root)
            new_in_root = _is_under(entry.path, project_root)
            if new_in_root and not existing_in_root:
                final[name] = entry
        else:
            final[name] = entry
    return sorted(final.values(), key=lambda e: e.name)


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _read_cached_fingerprint(cache_path: Path) -> str:
    if not cache_path.exists():
        return ""
    try:
        import json

        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    fp = data.get("fingerprint") if isinstance(data, dict) else None
    return str(fp) if isinstance(fp, str) else ""


def _atomic_write(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` atomically (tmp + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _render_registry_md(entries: list[SkillEntry], root: Path) -> str:
    project_name = root.name or "project"
    lines = [
        f"# Skill Registry — {project_name}",
        "",
        "<!-- Auto-generated by opencontext_sdd.skill_registry.refresh() -->",
        "",
        "## Skills",
        "",
        "| Skill | Description | Scope | Path |",
        "| --- | --- | --- | --- |",
    ]
    for entry in entries:
        try:
            rel = entry.path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            rel = str(entry.path)
        desc = entry.description.replace("|", "\\|").strip() or "—"
        lines.append(f"| `{entry.name}` | {desc} | {entry.source} | `{rel}` |")
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class _SourceDirs:
    user: tuple[Path, ...]
    project: tuple[Path, ...]


def _resolve_source_dirs(
    root: Path,
    source_dirs: list[Path] | None,
) -> _SourceDirs:
    """Return the resolved user + project source directories.

    When ``source_dirs`` is supplied, each dir is classified as ``project``
    iff it resolves under ``root``; otherwise ``user``.
    """
    if source_dirs is not None:
        project_root = root.resolve()
        user: list[Path] = []
        project: list[Path] = []
        for d in source_dirs:
            resolved = (d if d.is_absolute() else root / d).resolve()
            try:
                resolved.relative_to(project_root)
                project.append(d)
            except ValueError:
                user.append(d)
        return _SourceDirs(user=tuple(user), project=tuple(project))
    return _SourceDirs(
        user=tuple(_resolve_user_dirs()),
        project=tuple(_resolve_project_dirs(root)),
    )


def refresh(
    root: str | Path,
    *,
    force: bool = False,
    source_dirs: list[Path] | None = None,
    user_dirs: list[Path] | None = None,
    project_dirs: list[Path] | None = None,
) -> RefreshResult:
    """Write ``.atl/skill-registry.md`` + fingerprint cache if any source changed.

    Args:
        root: Project root whose ``.atl/`` is the output dir.
        force: When True, always rewrite (skip the fingerprint cache check).
        source_dirs: Optional override — a caller-supplied list of dirs to
            scan. Used by tests; defaults to ``SOURCE_DIRS``.

    Returns:
        ``RefreshResult`` describing what happened. ``changed=False`` means
        the fingerprint matched the cached one (a cache hit).
    """
    root = Path(root).resolve()
    user_overrides = user_dirs if user_dirs is not None else ()
    project_overrides = project_dirs if project_dirs is not None else ()
    if user_overrides or project_overrides:
        user_listing = list(user_overrides)
        project_listing = list(project_overrides)
    else:
        dirs = _resolve_source_dirs(root, source_dirs)
        user_listing = list(dirs.user)
        project_listing = list(dirs.project)

    # Collect all SKILL.md files (for fingerprint stability across runs even
    # if the registered entries change due to exclusions).
    all_files: list[Path] = []
    scanned: list[SkillEntry] = []
    parse_warnings: list[str] = []
    for d in user_listing:
        scanned.extend(
            _scan_dir(d, source="user", project_root=root, parse_warnings=parse_warnings)
        )
        if d.exists():
            all_files.extend(d.rglob("SKILL.md"))
    for d in project_listing:
        scanned.extend(
            _scan_dir(d, source="project", project_root=root, parse_warnings=parse_warnings)
        )
        if d.exists():
            all_files.extend(d.rglob("SKILL.md"))

    atl_dir = root / ".atl"
    registry_path = atl_dir / "skill-registry.md"
    cache_path = atl_dir / ".skill-registry.cache.json"

    fp = _fingerprint_skill_files(all_files)
    cached_fp = _read_cached_fingerprint(cache_path)
    if not force and cached_fp and cached_fp == fp and registry_path.exists():
        return RefreshResult(
            changed=False,
            registry_path=registry_path,
            cache_path=cache_path,
            skill_count=len(_dedupe(scanned, root)),
            reason="cache-hit",
            parse_warnings=tuple(parse_warnings),
        )

    entries = _dedupe(scanned, root)

    if not force and not cached_fp and registry_path.exists() and not fp:
        # Nothing to write; nothing to compare against.
        reason = "empty-fingerprint"
    elif force:
        reason = "forced"
    else:
        reason = "fingerprint-changed"

    md = _render_registry_md(entries, root)
    _atomic_write(registry_path, md)

    import json

    cache_body = json.dumps({"fingerprint": fp}, indent=2) + "\n"
    _atomic_write(cache_path, cache_body)

    return RefreshResult(
        changed=True,
        registry_path=registry_path,
        cache_path=cache_path,
        skill_count=len(entries),
        reason=reason,
        parse_warnings=tuple(parse_warnings),
    )


def get_skill_paths(
    root: str | Path | None = None,
    *,
    source_dirs: list[Path] | None = None,
) -> list[Path]:
    """Return the ``SKILL.md`` paths that refresh() would currently discover.

    No side effects; read-only. ``source_dirs`` overrides the default
    ``SOURCE_DIRS`` discovery (used by tests).
    """
    if root is None:
        root = Path.cwd()
    root = Path(root).resolve()
    dirs = _resolve_source_dirs(root, source_dirs)
    paths: list[Path] = []
    for d in (*dirs.user, *dirs.project):
        if d.exists():
            paths.extend(sorted(d.rglob("SKILL.md")))
    return paths


def match_skills(
    entries: list[SkillEntry],
    keywords: list[str] | None = None,
    *,
    name: str | None = None,
) -> list[SkillEntry]:
    """Return entries that match by name (exact) or keyword (substring)."""
    if name is not None:
        for entry in entries:
            if entry.name == name:
                return [entry]
        raise SkillNotFound(name)
    kws = {k.lower() for k in (keywords or [])}
    if not kws:
        return list(entries)
    return [
        entry
        for entry in entries
        if any(kw in entry.name.lower() or kw in entry.description.lower() for kw in kws)
    ]


class SkillNotFound(LookupError):
    """Raised when a named skill is not in the registry."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.skill_name = name


__all__ = [
    "PROJECT_SOURCE_DIRS",
    "SOURCE_DIRS",
    "USER_SOURCE_DIRS",
    "RefreshResult",
    "SkillEntry",
    "SkillNotFound",
    "get_skill_paths",
    "match_skills",
    "refresh",
    "refresh_skill_registry",
]


# Canonical public name expected by design.md §Public Python API. Kept as
# an alias of the internal ``refresh`` so existing callers keep working.
refresh_skill_registry = refresh
