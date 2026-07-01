"""Cache v2 — leaf guard (REQ-cache-v2-002).

``ast``-walk every ``.py`` file under ``cache/v2/`` and fail on any
import from a forbidden upward namespace (KG / Memory / Context /
Provider / Retrieval / Indexing). Used by ``tests/cache/v2/test_leaf.py``
as defense-in-depth on top of the repo-wide
``tests/architecture/test_no_upward_imports.py``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

# Namespaces the cache leaf must NOT import from (book doc 58 + PR-000.3
# cache-leaf invariant). Layer boundaries are downward-only; these are
# strictly above the cache leaf.
FORBIDDEN_UPWARD_NAMESPACES: tuple[str, ...] = (
    "opencontext_core.graph",
    "opencontext_core.memory",
    "opencontext_core.context",
    "opencontext_core.providers",
    "opencontext_core.retrieval",
    "opencontext_core.indexing",
)


@dataclass(frozen=True)
class LeafViolation:
    """One upward-import violation found by the leaf guard."""

    source: str
    target: str
    line: int


def _cache_v2_root() -> Path:
    return Path(__file__).resolve().parent


def _is_forbidden(module: str | None, forbidden: tuple[str, ...]) -> str | None:
    if not module:
        return None
    for ns in forbidden:
        if module == ns or module.startswith(ns + "."):
            return ns
    return None


def scan_module_for_upward_imports(
    *,
    module_path: Path,
    source: str,
    forbidden: tuple[str, ...] = FORBIDDEN_UPWARD_NAMESPACES,
) -> list[LeafViolation]:
    """Return every upward-import violation found in ``source``.

    ``module_path`` is reported as the violation source (relative posix).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out: list[LeafViolation] = []
    rel = module_path.as_posix()
    for node in ast.walk(tree):
        module: str | None = None
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                hit = _is_forbidden(module, forbidden)
                if hit:
                    out.append(LeafViolation(source=rel, target=module, line=node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = node.module
            hit = _is_forbidden(module, forbidden)
            if hit:
                out.append(LeafViolation(source=rel, target=module or "", line=node.lineno))
    return out


def verify_no_upward_imports(
    *,
    root: Path | None = None,
    forbidden: tuple[str, ...] = FORBIDDEN_UPWARD_NAMESPACES,
) -> list[LeafViolation]:
    """Walk every ``.py`` file under ``cache/v2/`` and return its violations."""
    base = root or _cache_v2_root()
    violations: list[LeafViolation] = []
    for path in sorted(base.rglob("*.py")):
        if path.name == __file__.split("/")[-1]:
            # Skip self — this file legitimately references the namespace list.
            continue
        rel = path.relative_to(base).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        violations.extend(
            scan_module_for_upward_imports(
                module_path=Path(rel),
                source=text,
                forbidden=forbidden,
            )
        )
    return violations


def raise_on_violation(violations: list[LeafViolation]) -> None:
    """Convenience: raise the first violation for CI / debug."""
    if not violations:
        return
    first = violations[0]
    raise LeafImportError(
        f"cache leaf violation: {first.source} imports {first.target!r} "
        f"at line {first.line}; cache leaf must be a strict leaf."
    )


class LeafImportError(RuntimeError):
    """Raised when the cache leaf imports an upward namespace."""


__all__ = [
    "FORBIDDEN_UPWARD_NAMESPACES",
    "LeafImportError",
    "LeafViolation",
    "raise_on_violation",
    "scan_module_for_upward_imports",
    "verify_no_upward_imports",
]