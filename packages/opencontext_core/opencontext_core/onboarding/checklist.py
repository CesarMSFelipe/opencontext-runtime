"""Developer-experience readiness checklist (PR-R2-D).

Spec: ``openspec/changes/opencontext-1-0-convergence/specs/developer-experience-onboarding/spec.md``
            REQ-dx-onb-001 (curated first-run journey), REQ-dx-onb-004
            (contributor commands discoverable).

A deterministic, side-effect-free readiness probe. Each ``ChecklistItem`` is
a small predicate (does config exist? are tests present? …). The overall
``DxChecklist.score`` is the weighted percentage of items that pass.

The checklist is the contract the wizard's ``verify`` step (REQ-dx-onb-001)
reports against. It is also what ``opencontext doctor`` calls when invoked
with ``--dx``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ChecklistItem:
    """A single readiness probe."""

    key: str
    label: str
    passed: bool
    weight: int = 1
    fix_hint: str = ""


@dataclass(frozen=True)
class DxChecklist:
    """A bundle of ``ChecklistItem``s + a weighted score in [0, 100]."""

    items: Sequence[ChecklistItem] = field(default_factory=tuple)

    @property
    def passed(self) -> int:
        return sum(1 for i in self.items if i.passed)

    @property
    def failed(self) -> int:
        return sum(1 for i in self.items if not i.passed)

    @property
    def total_weight(self) -> int:
        return sum(max(0, i.weight) for i in self.items)

    @property
    def passed_weight(self) -> int:
        return sum(max(0, i.weight) for i in self.items if i.passed)

    @property
    def score(self) -> int:
        total = self.total_weight
        if total == 0:
            return 0
        raw = (self.passed_weight * 100) / total
        # Clamp to [0, 100] so a buggy probe (e.g. negative weight) cannot
        # produce an out-of-range score that callers serialize as-is.
        return max(0, min(100, int(raw)))

    def find(self, key: str) -> ChecklistItem | None:
        """Return the item with this ``key`` or ``None``."""
        for item in self.items:
            if item.key == key:
                return item
        return None

    def fix_hints(self) -> list[str]:
        """Concatenated ``fix_hint`` of every failed item (in order)."""
        return [i.fix_hint for i in self.items if not i.passed and i.fix_hint]


# ---------------------------------------------------------------------------
# Built-in probes
# ---------------------------------------------------------------------------


def _has_file(path: Path) -> Callable[[Path], bool]:
    return lambda root: (root / path).exists()


def _has_dir(path: Path) -> Callable[[Path], bool]:
    return lambda root: (root / path).is_dir()


def _has_at_least_one_pytest(root: Path) -> bool:
    """``tests/`` exists with at least one ``test_*.py`` file."""
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return False
    return any(p.name.startswith("test_") and p.suffix == ".py" for p in tests_dir.iterdir())


# ``(key, label, probe, weight, fix_hint_if_failed)`` — the canonical 6-item
# readiness bundle for first-run. Order matters for stable scores across
# releases.
_DEFAULT_ITEMS: tuple[tuple[str, str, Callable[[Path], bool], int, str], ...] = (
    (
        "config",
        "opencontext.yaml present",
        _has_file(Path("opencontext.yaml")),
        25,
        "run `opencontext init` to create opencontext.yaml",
    ),
    (
        "sdd_context",
        ".opencontext/sdd/context.json present",
        _has_file(Path(".opencontext") / "sdd" / "context.json"),
        15,
        "run `opencontext init` to generate the SDD context",
    ),
    (
        "harness",
        ".opencontext/harness.yaml present",
        _has_file(Path(".opencontext") / "harness.yaml"),
        15,
        "run `opencontext init` to write the harness contract",
    ),
    (
        "gitignore",
        ".gitignore excludes .storage/ and .opencontext/",
        _has_file(Path(".gitignore")),
        10,
        "add `.storage/` and `.opencontext/` to .gitignore",
    ),
    (
        "tests",
        "tests/ with at least one test_*.py",
        _has_at_least_one_pytest,
        20,
        "create `tests/test_smoke.py` with at least one pytest",
    ),
    (
        "readme",
        "README.md present",
        _has_file(Path("README.md")),
        15,
        "create a README.md (one paragraph is enough)",
    ),
)


def run_checklist(root: str | Path) -> DxChecklist:
    """Run the built-in readiness checklist against ``root``.

    Returns a ``DxChecklist`` with one ``ChecklistItem`` per canonical probe.
    Side-effect-free: only ``stat`` calls, no writes.
    """
    root_path = Path(root).resolve()
    items: list[ChecklistItem] = []
    for key, label, probe, weight, fix_hint in _DEFAULT_ITEMS:
        try:
            passed = bool(probe(root_path))
        except OSError:
            passed = False
        items.append(
            ChecklistItem(
                key=key,
                label=label,
                passed=passed,
                weight=weight,
                fix_hint=fix_hint,
            )
        )
    return DxChecklist(items=tuple(items))


__all__ = ["ChecklistItem", "DxChecklist", "run_checklist"]
