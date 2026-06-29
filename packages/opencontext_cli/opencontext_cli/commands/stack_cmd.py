"""Stack CLI — detect the project's stack and prepare every agent for it.

`opencontext stack` detects the technology stack and renders concrete
engineering standards (formatter, static + dynamic reviewers, testing, code
standards). `--write` injects them as a managed block into AGENTS.md, so every
agent that honors the shared AGENTS.md convention works to the same standards
that OpenContext's verified-context gates assume.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from opencontext_cli.output import eprint
from opencontext_core.configurator.filemerge import (
    inject_managed_section,
    write_text_atomic,
)
from opencontext_core.dx.console_styles import console

_SECTION_ID = "stack"
# A real stack you work in matches several markers; one stray fixture file does
# not. Require ~2 markers' worth of confidence so polyglot/meta-repos don't emit
# standards for every language that appears in a test fixture.
_MIN_SCORE = 0.6


def add_stack_parser(subparsers: Any) -> None:
    """Add the ``stack`` command parser."""
    parser = subparsers.add_parser(
        "stack",
        help="Detect the stack and prepare agents with its engineering standards.",
        description=(
            "Detect the project's technology stack and render the engineering "
            "standards for it — formatter, static + dynamic reviewers, testing, "
            "and code standards.\n\n"
            "  opencontext stack            Print the detected standards\n"
            "  opencontext stack --write    Inject them into AGENTS.md (managed block)\n"
        ),
    )
    parser.add_argument("path", nargs="?", default=".", help="Project root to detect (default: .).")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the standards into AGENTS.md as a managed block (idempotent).",
    )


_PRUNE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".storage",
    ".opencontext",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "dist",
    "build",
    "target",
    "vendor",
    ".next",
    ".tox",
}


def _discover_paths(root: Path, *, max_files: int = 20_000) -> list[str]:
    """Project-relative file paths from one pruned walk.

    The profile detectors each re-walk the whole tree; detecting ~25 profiles on
    a large repo means ~25 full walks (including .storage/.git). Walk once here,
    skip heavy/vendored dirs, and hand the list to every detector — both faster
    and more correct (no markers matched inside vendored deps).
    """
    paths: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _PRUNE_DIRS and not d.startswith(".git")]
        base = Path(dirpath)
        for name in filenames:
            paths.append((base / name).relative_to(root).as_posix())
            if len(paths) >= max_files:
                return paths
    return paths


def _detect_profiles(root: Path) -> list[tuple[float, str]]:
    """All detected (score, profile) pairs, highest-confidence first.

    Reuses the same first-party detectors the indexer uses, so `stack` agrees
    with what `index` reports. Returns an empty list if the profiles package is
    unavailable (the renderer then falls back to generic standards).
    """
    try:
        from opencontext_profiles import first_party_profiles
    except ImportError:
        return []

    paths = _discover_paths(root)
    scored: list[tuple[float, str]] = []
    for profile in first_party_profiles():
        try:
            result = profile.detect(root, paths)
        except Exception:
            continue
        if result.score > 0:
            scored.append((result.score, result.profile))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return scored


def _select_stacks(
    scored: list[tuple[float, str]], known_profiles: frozenset[str]
) -> tuple[list[str], list[str]]:
    """Split detections into (chosen, dropped) by confidence + curated coverage.

    Chosen = curated stacks at or above the confidence threshold. If nothing
    clears the bar but a curated stack was detected, keep the single strongest so
    the output is never empty for a real (if small) project. Dropped names are
    returned only to tell the user honestly what was set aside.
    """
    known = [(score, name) for score, name in scored if name in known_profiles]
    chosen = [name for score, name in known if score >= _MIN_SCORE]
    if not chosen and known:
        chosen = [known[0][1]]
    dropped = [name for _, name in scored if name not in chosen]
    return chosen, dropped


def write_stack_standards(root: Path) -> tuple[bool, list[str]]:
    """Inject detected stack standards into ``root/AGENTS.md`` (managed block).

    Returns ``(changed, chosen_profiles)``. Reusable by both ``stack --write``
    and the setup flow. Raises ``ValueError`` if AGENTS.md is a symlink (the
    atomic writer refuses to follow it).
    """
    from opencontext_profiles.standards import KNOWN_PROFILES, render_stack_standards

    chosen, _ = _select_stacks(_detect_profiles(root), KNOWN_PROFILES)
    standards = render_stack_standards(chosen)
    agents_file = root / "AGENTS.md"
    existing = agents_file.read_text(encoding="utf-8") if agents_file.exists() else ""
    merged = inject_managed_section(existing, _SECTION_ID, standards)
    changed = write_text_atomic(agents_file, merged)
    return changed, chosen


def handle_stack(args: Any) -> int:
    """Dispatch the ``stack`` command. Returns a process exit code."""
    root = Path(args.path).resolve()
    if not root.is_dir():
        eprint(f"Not a directory: {root}")
        return 1

    try:
        from opencontext_profiles.standards import (
            KNOWN_PROFILES,
            render_stack_standards,
        )
    except ImportError:
        eprint("Stack standards require the opencontext-profiles package.")
        return 1

    if not args.write:
        chosen, dropped = _select_stacks(_detect_profiles(root), KNOWN_PROFILES)
        console.header("Stack Standards")
        if chosen:
            console.info(f"Detected stack: {', '.join(chosen)}")
        else:
            console.dim("No specific stack detected — showing general standards.")
        if dropped:
            console.dim(f"Lower-confidence, not included: {', '.join(dropped)}")
        console.print()
        console.print(render_stack_standards(chosen))
        console.dim("Run `opencontext stack --write` to add these to AGENTS.md.")
        return 0

    try:
        changed, chosen = write_stack_standards(root)
    except ValueError as exc:
        eprint(f"Refusing to write: {exc}")
        return 1

    detected = ", ".join(chosen) if chosen else "generic"
    agents_file = root / "AGENTS.md"
    console.header("Stack Standards")
    if changed:
        console.success(f"Updated {agents_file} with stack standards ({detected}).")
    else:
        console.dim(f"AGENTS.md already up to date ({detected}).")
    return 0
