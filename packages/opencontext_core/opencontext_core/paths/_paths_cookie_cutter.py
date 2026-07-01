"""Cookie-cutter AST rewriter for hardcoded storage path f-strings.

The v2 design (commit 003) wants modules with hardcoded
``.opencontext / .storage / .cache / .runtime`` path concatenations
rewritten to route through ``paths.resolve_storage_path_strict(Path)``.

This module is intentionally minimal: it ships an idempotent regex
pass that turns common patterns such as::

    f"{ROOT}/.opencontext/cache.db"
    f"{ROOT}/.storage/opencontext"
    f"{base}/.runtime/state.json"

into the resolver form::

    (Path(ROOT) / ".opencontext" / "cache.db").resolve()
    resolve_storage_path_strict(Path(ROOT))
    (Path(base) / ".runtime" / "state.json").resolve()

It is a scaffold intended to be invoked during code review / codemod
runs; it does NOT perform cross-module import insertion (the v1
importers need ``from opencontext_core.paths.resolve_paths import
resolve_storage_path_strict`` added per call site during commit 004
and 005 migrations).

Idempotency: ``rewrite_source(rewrite_source(s)) == rewrite_source(s)``.

Dry-run (A6): ``plan_rewrites(s)`` returns a list of planned changes
without mutating the source. Per A6 the migration MUST be previewed via
``plan_rewrites`` before any mass ``rewrite_source`` invocation.
"""

from __future__ import annotations

import re
from typing import Final

# Patterns matched: f"{...}/.opencontext/...", f"{...}/.storage/...",
# f"{...}/.cache/...", f"{...}/.runtime/...". Capture group 1 = the
# f-string expression stem (e.g. "{ROOT}" or "ROOT"); the suffix is one
# of the legacy path segments.
_DIRECTORIES: Final[tuple[str, ...]] = (".opencontext", ".storage", ".cache", ".runtime")

# regex per directory: matches `f"{X}/<dir>/<suffix>"` (suffix optional)
_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = tuple(
    (d, re.compile(r'f"(\{[^}]+\})/' + re.escape(d) + r'(?:/([^"\s]+))?"'))
    for d in _DIRECTORIES
)


def _replace(match: re.Match[str]) -> str:
    """Substitute one matched f-string with a resolver form."""
    expr = match.group(1)            # e.g. "{ROOT}"
    suffix = match.group(2)          # e.g. "cache.db" or None
    stem = re.sub(r"[{}]", "", expr)  # e.g. "ROOT"
    base = f"(Path({stem}))"
    if suffix:
        joined = " / ".join([f'"{dir_part}"' for dir_part in (suffix.split("/"))])
        return f"({base} / {joined}).resolve()"
    return f"resolve_storage_path_strict({base})"


def rewrite_source(source: str) -> str:
    """Apply the cookie-cutter rewrites to a single source string.

    Returns the source unchanged when no matches exist; otherwise returns
    the rewritten form. Running it twice on the same input is idempotent
    because the rewritten forms no longer match the patterns (the
    f-string is replaced with a non-matching expression).
    """
    out = source
    for _directory, pattern in _PATTERNS:
        out = pattern.sub(_replace, out)
    return out


def plan_rewrites(source: str) -> list[dict[str, object]]:
    """A6 dry-run: report planned rewrites without mutating the source.

    Returns a list of plan entries with ``directory``, ``line`` (1-based),
    ``original`` (the matched f-string snippet) and ``replacement`` (the
    would-be rewrite). The source string is not touched.
    """
    plan: list[dict[str, object]] = []
    for lineno, line_text in enumerate(source.splitlines(keepends=True), start=1):
        for directory, pattern in _PATTERNS:
            for match in pattern.finditer(line_text):
                plan.append(
                    {
                        "directory": directory,
                        "line": lineno,
                        "original": match.group(0),
                        "replacement": _replace(match),
                    }
                )
    return plan


__all__ = ["plan_rewrites", "rewrite_source"]  
