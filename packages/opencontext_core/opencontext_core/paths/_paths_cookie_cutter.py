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
_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(
        r'f"(\{[^}]+\})/' + re.escape(d) + r'(?:/([^"\s]+))?"'
    )
    for d in _DIRECTORIES
)


def rewrite_source(source: str) -> str:
    """Apply the cookie-cutter rewrites to a single source string.

    Returns the source unchanged when no matches exist; otherwise returns
    the rewritten form. Running it twice on the same input is idempotent
    because the rewritten forms no longer match the patterns (the
    f-string is replaced with a non-matching expression).
    """
    out = source
    for pattern in _PATTERNS:
        out = pattern.sub(_replace, out)
    return out


def _replace(match: re.Match[str]) -> str:
    """Substitute one matched f-string with a resolver form."""
    expr = match.group(1)            # e.g. "{ROOT}"
    suffix = match.group(2)          # e.g. "cache.db" or None
    stem = re.sub(r"[{}]", "", expr) # e.g. "ROOT"
    base = f"(Path({stem}))"
    if suffix:
        joined = " / ".join([f'"{dir_part}"' for dir_part in (suffix.split("/"))])
        return f"{base} / {joined}".replace(
            f"{base} / {joined}", f"({base} / {joined}).resolve()"
        )
    return f"resolve_storage_path_strict({base})"


__all__ = ["rewrite_source"]
