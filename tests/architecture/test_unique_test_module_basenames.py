"""Architecture guard: pytest module names under tests/ must be unique.

pytest's default (prepend) import mode derives a module name for each test
file by walking up from the file while ``__init__.py`` exists. Two files in
different ``__init__.py``-less directories that share a basename (for example
``tests/executors/test_registry.py`` and ``tests/workflows/test_registry.py``)
resolve to the same module name, which aborts collection of the whole suite
with "import file mismatch". This test pins that invariant so a duplicate
basename fails one focused test instead of breaking full-suite collection.

Fixture repos excluded from collection via ``collect_ignore_glob`` in a
conftest (acceptance/golden test data) are exempt — pytest never imports them.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from fnmatch import fnmatch
from pathlib import Path

# Repo root is two levels up from this file (tests/architecture/).
_REPO_ROOT = Path(__file__).parent.parent.parent
_TESTS_DIR = _REPO_ROOT / "tests"


def _collect_ignore_globs() -> list[tuple[Path, str]]:
    """Return (conftest_dir, pattern) pairs from every tests/ conftest."""
    pairs: list[tuple[Path, str]] = []
    for conftest in _TESTS_DIR.rglob("conftest.py"):
        tree = ast.parse(conftest.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "collect_ignore_glob" not in targets:
                continue
            try:
                patterns = ast.literal_eval(node.value)
            except ValueError:
                continue
            pairs.extend((conftest.parent, str(p)) for p in patterns)
    return pairs


def _is_collection_ignored(path: Path, globs: list[tuple[Path, str]]) -> bool:
    """True when a conftest ``collect_ignore_glob`` pattern excludes ``path``."""
    for base, pattern in globs:
        if not path.is_relative_to(base):
            continue
        if fnmatch(path.relative_to(base).as_posix(), pattern):
            return True
    return False


def _prepend_mode_module_name(path: Path) -> str:
    """Return the module name pytest assigns in prepend import mode."""
    parts = [path.stem]
    current = path.parent
    while (current / "__init__.py").is_file():
        parts.append(current.name)
        current = current.parent
    return ".".join(reversed(parts))


def test_test_module_names_are_unique() -> None:
    """No two collected test files may resolve to the same pytest module name."""
    globs = _collect_ignore_globs()
    by_module: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(_TESTS_DIR.rglob("test_*.py")):
        if "__pycache__" in path.parts or _is_collection_ignored(path, globs):
            continue
        by_module[_prepend_mode_module_name(path)].append(path)

    collisions = {
        module: [str(p.relative_to(_REPO_ROOT)) for p in paths]
        for module, paths in by_module.items()
        if len(paths) > 1
    }
    assert not collisions, (
        "Duplicate pytest module names break full-suite collection "
        "(import file mismatch). Rename the file or add __init__.py:\n"
        + "\n".join(f"{module}: {paths}" for module, paths in sorted(collisions.items()))
    )
