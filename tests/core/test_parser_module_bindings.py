"""Module-level constants/registries are indexed as symbols.

A symbol search that only knows functions and classes is blind to a file that
"defines" things as data (PERSONAS = (...), DEFAULT_X = [...]). These bindings
are the answer to "where is X defined" for registry/config modules, so the
parser must surface them with both the name and a snippet of the value.
"""

from __future__ import annotations

from opencontext_core.indexing.tree_sitter_parser import TreeSitterParser

SOURCE = '''\
"""Module docstring."""

ALPHA = "OC Orchestrator"
_PRIVATE = {"k": "v"}
A, B = 1, 2


def helper() -> None:
    local_only = 123  # must NOT be indexed (function-local)
    return None


class Thing:
    attr = 1  # class attribute, not module-level
'''


def _symbols():
    parser = TreeSitterParser()
    if not parser.is_available():
        return None
    return parser.parse_file_status("m.py", SOURCE).symbols


def test_module_constants_indexed_with_value_snippet() -> None:
    symbols = _symbols()
    if symbols is None:
        return  # tree-sitter unavailable; regex fallback covered elsewhere
    by_name = {s.name: s for s in symbols}

    assert "ALPHA" in by_name
    assert by_name["ALPHA"].kind == "constant"
    assert by_name["ALPHA"].is_exported is True
    # The assigned value is searchable (FTS matches "Orchestrator" via signature).
    assert "OC Orchestrator" in (by_name["ALPHA"].signature or "")

    # Tuple unpacking binds each name.
    assert "A" in by_name and "B" in by_name

    # Underscore-prefixed bindings are indexed but not exported.
    assert "_PRIVATE" in by_name
    assert by_name["_PRIVATE"].is_exported is False


def test_function_locals_are_not_indexed() -> None:
    symbols = _symbols()
    if symbols is None:
        return
    names = {s.name for s in symbols}
    assert "local_only" not in names  # locals would explode the index
    assert "helper" in names  # the function itself is still indexed
