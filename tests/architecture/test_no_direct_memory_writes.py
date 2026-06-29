"""AVH-001 / AVH-002 fitness guard — the MemoryHarness is the sole durable writer.

Only ``memory/harness.py`` may call ``<store>.write`` / ``<store>.supersede`` on a
memory store. Every other site under the ``memory/`` package must route durable
writes through the harness (``MemoryHarness.write`` / ``.promote``), so the AVH-002
``MemoryStoreProvider.write`` bypass — a direct ``self._store.write(record)`` that
skipped the conflict-check, KG-link and receipt — can never be reintroduced silently.

A frozen ratchet (:data:`MEMORY_WRITE_RATCHET`) records the pre-existing legacy
direct-write sites kept verbatim until ``memory_v2_enabled`` flips, each keyed by
``(relative_path, method)`` with a documented reason. A NEW direct write at any
non-allowlisted ``(file, method)`` fails the guard — the same ratchet philosophy as
``ALLOWED_UPWARD`` in ``test_no_upward_imports.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

MEMORY = (
    Path(__file__).resolve().parents[2]
    / "packages/opencontext_core/opencontext_core/memory"
)

#: The single sanctioned durable writer (book OC-MEMORY-001 §8/§10).
ALLOWED_WRITERS: frozenset[str] = frozenset({"harness.py"})

#: Durable mutation verbs on a memory store.
WRITE_METHODS: frozenset[str] = frozenset({"write", "supersede"})

#: Frozen ratchet of pre-existing legacy direct ``<store>.{write,supersede}`` sites,
#: keyed ``(memory-relative path, method)`` with a reason. New sites NOT listed fail.
MEMORY_WRITE_RATCHET: dict[tuple[str, str], str] = {
    ("composite.py", "write"): (
        "CompositeStore is itself a store backend; write fans out to the wrapped stores"
    ),
    ("harvester.py", "write"): (
        "legacy direct harvester writes kept verbatim until memory_v2_enabled flips "
        "(see config.py memory_v2_enabled note)"
    ),
    ("provider.py", "supersede"): (
        "supersede composes the store's deterministic supersession path; AVH-002 routes "
        "write() through the harness, supersede ratcheted for a follow-up"
    ),
}


def _receiver_name(value: ast.AST) -> str | None:
    """Best-effort receiver name for ``recv.method(...)`` (Name.id or Attribute.attr)."""
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return None


def _is_store_write(node: ast.AST) -> tuple[str, ...] | None:
    """Return ``(method,)`` when *node* is a ``<...store>.{write,supersede}(...)`` call."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return None
    if node.func.attr not in WRITE_METHODS:
        return None
    recv = _receiver_name(node.func.value)
    if recv and recv.endswith("store"):
        return (node.func.attr,)
    return None


def _direct_memory_writes() -> dict[tuple[str, str], list[int]]:
    """Map every direct memory ``<store>.{write,supersede}`` site outside the harness."""
    found: dict[tuple[str, str], list[int]] = {}
    for py in MEMORY.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        rel = py.name if py.parent == MEMORY else str(py.relative_to(MEMORY))
        if rel in ALLOWED_WRITERS:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            hit = _is_store_write(node)
            if hit is not None:
                found.setdefault((rel, hit[0]), []).append(node.lineno)
    return found


def test_memory_harness_is_sole_writer() -> None:
    """No direct memory store write/supersede outside the harness or the ratchet."""
    found = _direct_memory_writes()
    new = {k: v for k, v in found.items() if k not in MEMORY_WRITE_RATCHET}
    assert not new, (
        "Direct memory store writes outside MemoryHarness — route through "
        "MemoryHarness.write (AVH-002):\n"
        + "\n".join(
            f"  memory/{rel} : {method}() at line(s) {lines}"
            for (rel, method), lines in sorted(new.items())
        )
    )


def test_guard_flags_a_seeded_bypass() -> None:
    """The detector itself must FAIL on the AVH-002 bug shape (direct store.write)."""
    seeded = (
        "class Bypass:\n"
        "    def write(self, record):\n"
        "        return self._store.write(record)\n"
    )
    tree = ast.parse(seeded)
    hits = [n for n in ast.walk(tree) if _is_store_write(n) is not None]
    assert hits, "guard must detect a direct <store>.write(...) bypass"
