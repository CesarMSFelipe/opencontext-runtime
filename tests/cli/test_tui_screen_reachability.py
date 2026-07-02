"""TUI screen reachability and binding hygiene guards.

Two contracts:

1. **Nav-reachability**: every class exported in
   ``opencontext_cli.tui.screens.__all__`` must be reachable (i.e. appear in a
   ``push_screen`` call) within the CLI TUI source tree.  Unreachable exports
   are dead code that mislead readers.

2. **No pass-stub bindings**: no ``BINDINGS`` entry in a TUI screen class may
   map to an ``action_*`` method whose body is effectively a no-op (only
   ``pass`` or a bare docstring).  Shipping a dead key in the footer is
   misleading for users.

Both checks are static (AST) — they run without a display or Textual runtime.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator

_REPO_ROOT = Path(__file__).parent.parent.parent
_TUI_ROOT = _REPO_ROOT / "packages" / "opencontext_cli" / "opencontext_cli" / "tui"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tui_sources() -> Iterator[tuple[Path, str]]:
    """Yield (path, source) for every .py in the TUI tree (excluding tests/build)."""
    for path in _TUI_ROOT.rglob("*.py"):
        parts = path.parts
        if "tests" in parts or "build" in parts:
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except Exception:
            pass


def _push_screen_class_names(source: str) -> set[str]:
    """Return class names that appear as the first arg to any push_screen() call."""
    names: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "push_screen"):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        # push_screen(SomeScreen(...))
        if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name):
            names.add(arg.func.id)
        # push_screen(SomeScreen)  — bare class
        elif isinstance(arg, ast.Name):
            names.add(arg.id)
    return names


def _is_pass_stub(func_def: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if the function body contains no real statements (just pass/…/docstring)."""
    stmts = func_def.body
    real: list[ast.stmt] = []
    for s in stmts:
        # Strip leading docstring
        if (
            isinstance(s, ast.Expr)
            and isinstance(s.value, ast.Constant)
            and isinstance(s.value.value, str)
        ):
            continue
        real.append(s)
    if not real:
        return True
    return len(real) == 1 and isinstance(real[0], ast.Pass)


def _binding_actions_in_class(cls: ast.ClassDef) -> list[str]:
    """Return action strings from the BINDINGS ClassVar of a screen class.

    BINDINGS may be either a plain ``ast.Assign`` or an ``ast.AnnAssign``
    (when annotated as ``ClassVar[...]``); both forms are handled.
    """
    actions: list[str] = []

    def _extract_from_value(value: ast.expr) -> None:
        if not isinstance(value, ast.List):
            return
        for elt in value.elts:
            # Binding(key, action, ...) — action is the second positional arg
            if isinstance(elt, ast.Call) and elt.args and len(elt.args) >= 2:
                action_node = elt.args[1]
                if isinstance(action_node, ast.Constant) and isinstance(action_node.value, str):
                    actions.append(action_node.value)
            # ("key", "action") or ("key", "action", "description") tuples
            elif isinstance(elt, ast.Tuple) and len(elt.elts) >= 2:
                action_node = elt.elts[1]
                if isinstance(action_node, ast.Constant) and isinstance(action_node.value, str):
                    actions.append(action_node.value)

    for node in ast.walk(cls):
        # Plain assignment: BINDINGS = [...]
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name) and t.id == "BINDINGS"]
            if targets:
                _extract_from_value(node.value)
        # Annotated assignment: BINDINGS: ClassVar[...] = [...]
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "BINDINGS":
                if node.value is not None:
                    _extract_from_value(node.value)

    return actions


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_all_exported_tui_screens_are_nav_reachable() -> None:
    """Every Screen subclass in tui.screens.__all__ must appear in a push_screen() call."""
    from textual.screen import Screen

    import opencontext_cli.tui.screens as screens_mod

    # Only check actual Screen subclasses — enums/helpers in __all__ are excluded.
    exported_screens = [
        name
        for name in screens_mod.__all__
        if isinstance(getattr(screens_mod, name, None), type)
        and issubclass(getattr(screens_mod, name), Screen)
    ]

    reachable: set[str] = set()
    for _path, src in _tui_sources():
        reachable |= _push_screen_class_names(src)

    unreachable = [name for name in exported_screens if name not in reachable]
    assert not unreachable, (
        "These exported TUI screen classes are not reachable via any push_screen() call:\n"
        + "\n".join(f"  {name}" for name in sorted(unreachable))
        + "\nEither wire them into a navigation action or remove them from __all__."
    )


def test_no_pass_stub_bindings_in_tui_screens() -> None:
    """No BINDINGS entry may map to an action_* method that is only pass."""
    violations: list[str] = []
    for path, src in _tui_sources():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bound_actions = _binding_actions_in_class(node)
            # Build method lookup
            methods: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
            for item in ast.walk(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods[item.name] = item
            for action in bound_actions:
                method_name = f"action_{action}"
                method = methods.get(method_name)
                if method is not None and _is_pass_stub(method):
                    rel = path.relative_to(_REPO_ROOT)
                    violations.append(
                        f"{rel}: {node.name}.{method_name} — binding '{action}' maps to a pass-stub"
                    )
    assert not violations, (
        "Found pass-stub action methods mapped to BINDINGS entries:\n"
        + "\n".join(violations)
        + "\nRemove the binding or implement the action."
    )
