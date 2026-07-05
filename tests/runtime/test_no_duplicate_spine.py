"""Amendment A2: single-owner gate for RuntimeApi.

Forbids a parallel ``runtime/spine.py``. Exactly one ``class RuntimeApi``
must exist in ``opencontext_core/runtime/``, declared in
``runtime/api.py``.
"""

from __future__ import annotations

from pathlib import Path


def _runtime_dir() -> Path:
    """Locate ``opencontext_core/runtime/`` from this test file's path.

    ``tests/runtime/test_no_duplicate_spine.py`` -> parents[2] is the repo
    root; ``<root>/packages/opencontext_core/opencontext_core/runtime/`` is
    the canonical location.
    """
    root = Path(__file__).resolve().parents[2]
    return root / "packages" / "opencontext_core" / "opencontext_core" / "runtime"


def test_single_runtime_api_class() -> None:
    """Exactly one ``class RuntimeApi`` declaration exists in runtime/.

    Walks every ``.py`` file under ``opencontext_core/runtime/`` (excluding
    ``__pycache__``) and counts the literal substring ``class RuntimeApi``.
    Amendment A2 single-owner gate.
    """
    runtime_dir = _runtime_dir()
    assert runtime_dir.is_dir(), f"runtime dir not found: {runtime_dir}"

    owners: list[str] = []
    for path in sorted(runtime_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "class RuntimeApi" in text:
            owners.append(path.relative_to(runtime_dir.parent).as_posix())

    assert owners == ["runtime/api.py"], (
        f"RuntimeApi must live in exactly one file under runtime/; "
        f"found in: {owners} (amendment A2 forbids duplicates)"
    )
