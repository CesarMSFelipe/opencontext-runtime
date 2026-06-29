"""Ponytail guard — the bespoke cache layer must NOT duplicate stdlib memoization.

The bespoke ``CacheEntry`` layer is reserved for what ``functools.lru_cache`` /
``@cache`` cannot do (cross-run, file-invalidated, provenance-bearing,
policy-gated). In-process pure memoization stays on stdlib and must not be
re-implemented here.
"""

from __future__ import annotations

import ast
from pathlib import Path

from opencontext_core.context import signature_compression
from opencontext_core.context.signature_compression import _load_parser

_CACHE_PKG = Path(signature_compression.__file__).parent.parent / "cache"


def _decorator_names(source: str) -> set[str]:
    """Return the set of decorator names used on functions/classes in ``source``."""
    names: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            for deco in node.decorator_list:
                target = deco.func if isinstance(deco, ast.Call) else deco
                if isinstance(target, ast.Name):
                    names.add(target.id)
                elif isinstance(target, ast.Attribute):
                    names.add(target.attr)
    return names


# The new cross-run cache modules added by PR-000.3.
_NEW_MODULES = (
    "store.py",
    "tool_cache.py",
    "ast_cache.py",
    "provider_cache.py",
    "keyed.py",
    "invalidation.py",
)


def test_parser_object_is_already_lru_cached() -> None:
    # The tree-sitter parser *object* load is memoized by stdlib; AstCache must
    # not re-implement parser loading — it caches parse *results* instead.
    assert hasattr(_load_parser, "cache_info")
    assert hasattr(_load_parser, "cache_clear")


def test_new_cache_modules_add_no_in_process_memoization() -> None:
    for name in _NEW_MODULES:
        source = (_CACHE_PKG / name).read_text(encoding="utf-8")
        decorators = _decorator_names(source)
        assert "lru_cache" not in decorators, f"{name} must not add stdlib-duplicating memoization"
        assert "cache" not in decorators, f"{name} must not add stdlib-duplicating memoization"


def test_ast_cache_does_not_reimplement_parser_loading() -> None:
    source = (_CACHE_PKG / "ast_cache.py").read_text(encoding="utf-8")
    # AstCache is a result cache; it must not import tree-sitter or load parsers.
    assert "tree_sitter" not in source
    assert "import tree_sitter" not in source
