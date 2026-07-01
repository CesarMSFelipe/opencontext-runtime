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

import ast
import re
from pathlib import Path
from typing import Final

# Patterns matched: f"{...}/.opencontext/...", f"{...}/.storage/...",
# f"{...}/.cache/...", f"{...}/.runtime/...". Capture group 1 = the
# f-string expression stem (e.g. "{ROOT}" or "ROOT"); the suffix is one
# of the legacy path segments.
_DIRECTORIES: Final[tuple[str, ...]] = (".opencontext", ".storage", ".cache", ".runtime")

# regex per directory: matches `f"{X}/<dir>/<suffix>"` (suffix optional)
_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = tuple(
    (d, re.compile(r'f"(\{[^}]+\})/' + re.escape(d) + r'(?:/([^"\s]+))?"')) for d in _DIRECTORIES
)

# ---------------------------------------------------------------------------
# AST scanner (amendment-3 P1.5 — source-of-truth gate)
# ---------------------------------------------------------------------------

#: Productive code root — the AST scanner walks here. The scan does NOT look
#: inside the ``paths/`` subpackage itself: it is the sanctioned owner of the
#: resolver symbols and the cookie-cutter docstring.
PROD_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

#: Top-level directory names excluded from the AST scan.
ALLOWLIST_TOP: Final[frozenset[str]] = frozenset(
    {"tests", "docs", "examples", "benchmarks", "__pycache__", "build", "dist"}
)

#: Forbidden path segments (productive code must route through the resolver).
_FORBIDDEN_TOKENS: Final[frozenset[str]] = frozenset(_DIRECTORIES)

#: Function names whose argument is a hardcoded path call (open, sqlite3.connect).
_PATH_CALL_NAMES: Final[frozenset[str]] = frozenset({"open"})

#: Sanctioned path-construction owners — the resolver itself + cookie-cutter.
#: Files matching these prefixes are excluded from the AST scan.
_OWNER_PREFIXES: Final[tuple[str, ...]] = (
    "opencontext_core/opencontext_core/paths/__init__.py",
    "opencontext_core/opencontext_core/paths/resolve_paths.py",
    "opencontext_core/opencontext_core/paths/_paths_cookie_cutter.py",
)


def _replace(match: re.Match[str]) -> str:
    """Substitute one matched f-string with a resolver form."""
    expr = match.group(1)  # e.g. "{ROOT}"
    suffix = match.group(2)  # e.g. "cache.db" or None
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


# ---------------------------------------------------------------------------
# AST scanner (amendment-3 P1.5 — see design.md AC#2 / commit-003 tasks)
# ---------------------------------------------------------------------------


def _is_docstring(node: ast.AST) -> bool:
    """True when *node* is a bare string constant (module/function/class docstring)."""
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)


def _string_contains_forbidden(node: ast.AST | None) -> str | None:
    """Return the forbidden token when *node* is a string literal carrying one.

    Inspects ONLY the ``Constant`` / ``FormattedValue`` / ``JoinedStr``
    leaves of *node* — never attribute accesses like ``x.storage.mode``,
    which would otherwise be flagged by naive substring matching.
    """
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        for token in _FORBIDDEN_TOKENS:
            if token in node.value:
                return token
        return None
    if isinstance(node, ast.JoinedStr):
        for part in node.values:
            tok = _string_contains_forbidden(part)
            if tok is not None:
                return tok
        return None
    if isinstance(node, ast.BinOp):
        # string concatenation only — flag if either side carries a token
        # in its STRING operand; ignore attribute accesses etc.
        tok = _string_contains_forbidden(node.left)
        if tok is not None:
            return tok
        tok = _string_contains_forbidden(node.right)
        if tok is not None:
            return tok
        return None
    return None


def _violates(node: ast.AST) -> tuple[str, str] | None:
    """Return ``(shape, snippet)`` when *node* constructs a forbidden path.

    Shapes detected:
      * ``ast.BinOp`` with ``Div`` op and a forbidden-segment right operand
        (e.g. ``Path(root) / ".storage"``).
      * ``ast.Call`` to ``open(...)`` whose first positional argument is an
        f-string or BinOp containing a forbidden segment
        (e.g. ``open(f"{root}/.storage/x.db")``).
      * ``ast.Call`` to ``*.connect(...)`` whose first positional argument
        is an f-string or BinOp containing a forbidden segment
        (e.g. ``sqlite3.connect(f"{root}/.storage/x.db")``).

    Dedup of chained ``A / B / C`` BinOps happens in
    :func:`scan_hardcoded_paths` (one finding per ``(file, line)``); the
    walker may emit multiple BinOp hits on the same line.
    """
    # Path(root) / ".storage"  ->  ast.BinOp(Div, _, Constant)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        # Walk the chain looking for any forbidden-string constant in the
        # right operands; first hit wins.
        token = _find_forbidden_in_div_chain(node)
        if token is not None:
            return ("Path()/'.x'", token)

    # open(f"{root}/.storage/x") / sqlite3.connect(f"{root}/.storage/x")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "connect":
            # Match sqlite3.connect / connector.connect — qualified receiver.
            if node.args:
                token = _string_contains_forbidden(node.args[0])
                if token is not None:
                    return ("DB connect", token)
        if node.func.attr in _PATH_CALL_NAMES:
            if node.args:
                token = _string_contains_forbidden(node.args[0])
                if token is not None:
                    return ("open()", token)

    # Bare `open(...)` written as Name
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "open" and node.args:
            token = _string_contains_forbidden(node.args[0])
            if token is not None:
                return ("open()", token)

    return None


def _find_forbidden_in_div_chain(node: ast.BinOp) -> str | None:
    """Walk the right operands of a ``/``-chain for any forbidden token.

    For ``Path(root) / ".opencontext" / "sessions"`` the chain has BinOps
    with right operands ``".opencontext"`` then ``"sessions"``. The first
    forbidden hit is the one to report. Attribute accesses on the left
    side (``x.storage``) are ignored — they only matter when they appear
    inside a string literal.
    """
    current: ast.AST = node
    while isinstance(current, ast.BinOp) and isinstance(current.op, ast.Div):
        token = _string_contains_forbidden(current.right)
        if token is not None:
            return token
        current = current.left
    return None


def _is_leftmost_div(node: ast.BinOp) -> bool:
    """True when *node* is the LEFTMOST ``BinOp`` with ``Div`` in its chain.

    AST layout for chained ``A / B / C``::

        BinOp(left=BinOp(left=A, op=Div, right=B), op=Div, right=C)
              ^------------------------------^--------------------^
              outer.left (a BinOp-Div)        outer.right (C)

    The OUTERMOST (root of the chain) has ``left`` that IS another
    BinOp-Div; the LEFTMOST (innermost) has ``left`` that is a Name /
    Call / Constant.

    Note: dedup of chain-emitted findings happens in
    :func:`scan_hardcoded_paths` (one finding per ``(file, line)``),
    not in this helper — the helper only tags the leftmost BinOp for
    tests that want to verify the chain structure.
    """
    return not (isinstance(node.left, ast.BinOp) and isinstance(node.left.op, ast.Div))


def _is_productive(path: Path) -> bool:
    """True when *path* is productive code (not a test/docs/example/bench/cache)."""
    return not any(part in ALLOWLIST_TOP for part in path.parts)


def scan_hardcoded_paths(
    root: Path | None = None,
) -> list[tuple[str, int, str]]:
    """AST-scan productive code for hardcoded ``.opencontext`` / ``.storage`` / etc.

    Amendment-3 P1.5 source-of-truth gate (design.md acceptance criterion #2).
    Returns a list of ``(relative_path, lineno, shape)`` tuples for every
    productive-code node that hand-builds a forbidden storage path.

    Allowlist:
      * top-level dirs in :data:`ALLOWLIST_TOP` (``tests``, ``docs``,
        ``examples``, ``benchmarks``, ``__pycache__``, ``build``, ``dist``);
      * the sanctioned path-construction owners in
        :data:`_OWNER_PREFIXES` (resolver + cookie-cutter);
      * docstrings (``ast.Expr`` of a bare ``ast.Constant``).

    Dedup: a chained ``A / B / C`` BinOp emits one BinOp-node per nested
    level on the same line; the dedup step keeps ONE finding per
    ``(file, line)`` so the chain shows up exactly once.
    """
    prod_root = Path(root) if root is not None else PROD_ROOT
    findings: list[tuple[str, int, str]] = []
    seen_keys: set[tuple[str, int]] = set()
    for path in sorted(prod_root.rglob("*.py")):
        if not _is_productive(path):
            continue
        rel = path.relative_to(prod_root.parent).as_posix()
        # Compute the package-relative path for owner-prefix matching
        # (the OWNER_PREFIXES values are relative to prod_root, not its
        # parent — otherwise tmp_path-based tests wouldn't see them).
        pkg_rel = path.relative_to(prod_root).as_posix()
        if any(
            pkg_rel == prefix.removeprefix("opencontext_core/") or pkg_rel == prefix
            for prefix in _OWNER_PREFIXES
        ):
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.expr) and not isinstance(node, ast.Call):
                # Skip non-expression / non-call nodes that the walker may
                # surface (e.g. ast.stmt) — they don't carry lineno-bearing
                # path construction.
                continue
            if _is_docstring(node):
                continue
            hit = _violates(node)
            if hit is not None:
                key = (rel, node.lineno)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                shape, snippet = hit
                findings.append((rel, node.lineno, f"{shape}: {snippet!r}"))
    return findings


__all__ = ["plan_rewrites", "rewrite_source", "scan_hardcoded_paths"]
