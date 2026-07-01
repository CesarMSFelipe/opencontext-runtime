"""AST-based paths gate (production code scan).

Amendment-2 source-of-truth gate: structural AST scan over productive code
catches hardcoded ``.opencontext / .storage / .cache / .runtime`` path
strings that the older grep gate misses (f-strings, BinOp concatenated
paths). The grep gate remains as a cheap smoke check but this AST scan
is the contract that ships with commit 003.

Allowlist
---------
- ``tests/``, ``docs/``, ``benchmarks/``, ``examples/`` path parts
- ``.md``, ``.rst`` suffixes
- AST ``Expr(Constant)`` (docstrings / standalone string statements)
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path("packages/opencontext_core/opencontext_core")
FORBIDDEN_TOKENS = (".opencontext", ".storage", ".cache", ".runtime")
ALLOWLIST_PATH_PARTS = ("tests/", "docs/", "benchmarks/", "examples/")
ALLOWLIST_SUFFIXES = (".md", ".rst")

# Migration cap (amendment-2). The AST scan is the source-of-truth gate;
# the count MUST monotonically decrease as migration commits (004, 005, …)
# rewire callers to ``paths.resolve_storage_path``. The cap is the v2
# Phase-1 starting point and is tightened as commits land; commit 016's
# acceptance gate drives it to zero.
_MIGRATION_CAP = 350


def _is_productive(path: Path) -> bool:
    s = str(path)
    if any(part in s for part in ALLOWLIST_PATH_PARTS):
        return False
    if path.suffix in ALLOWLIST_SUFFIXES:
        return False
    return True


def _violates(node: ast.AST) -> bool:
    # JoinedStr (f-string): scan its values for forbidden tokens
    if isinstance(node, ast.JoinedStr):
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                if any(t in v.value for t in FORBIDDEN_TOKENS):
                    return True
    # BinOp = "x" + "/.storage/y" or Path(root) / ".storage"
    if isinstance(node, ast.BinOp):
        try:
            left = ast.unparse(node.left)
            right = ast.unparse(node.right)
        except Exception:
            return False
        return any(t in (left + right) for t in FORBIDDEN_TOKENS)
    return False


def _should_skip(node: ast.AST) -> bool:
    # Skip bare docstrings / standalone string statements (Expr(Constant)).
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)


def scan_hardcoded_paths() -> list[tuple[str, int, str]]:
    findings: list[tuple[str, int, str]] = []
    if not ROOT.exists():
        return findings
    for path in ROOT.rglob("*.py"):
        if not _is_productive(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if _should_skip(node):
                continue
            if _violates(node):
                findings.append((str(path), node.lineno, ast.dump(node)[:120]))
    return findings


def test_ast_finds_zero_hardcoded_paths() -> None:
    """AST gate is the source of truth (Amendment-2): cap-bound count.

    Production callers must route every
    ``.opencontext / .storage / .cache / .runtime`` access through
    ``paths.resolve_storage_path`` / ``paths.resolve_workspace_path``.
    The Phase-1 cap allows the v1 baseline; commits 004 + 005 lower it.
    """
    findings = scan_hardcoded_paths()
    assert len(findings) <= _MIGRATION_CAP, (
        f"AST hardcoded-path findings grew to {len(findings)} (cap "
        f"{_MIGRATION_CAP}); commits 004/005 must reduce it. "
        "First 20:\n"
        + "\n".join(f"{p}:{ln}" for p, ln, _ in findings[:20])
    )
