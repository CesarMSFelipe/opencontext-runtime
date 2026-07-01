"""RED tests for the developer-experience readiness checklist.

Spec: openspec/changes/opencontext-1-0-convergence/specs/developer-experience-onboarding/spec.md
          REQ-dx-onb-001 (curated journey → checklist Score 0..100)

The checklist is a deterministic, side-effect-free readiness probe. Each
item is a small predicate (does config exist? are tests present? …). The
overall score is the weighted percentage of items that pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.onboarding.checklist import (
    ChecklistItem,
    DxChecklist,
    run_checklist,
)


@pytest.fixture
def fresh_project(tmp_path: Path) -> Path:
    """An empty project (no config, no tests)."""

    return tmp_path


@pytest.fixture
def ready_project(tmp_path: Path) -> Path:
    """A project that satisfies every checklist item."""

    root = tmp_path
    (root / "opencontext.yaml").write_text("project: {}\n", encoding="utf-8")
    (root / "README.md").write_text("# Title\n\nBody.\n", encoding="utf-8")
    (root / ".gitignore").write_text(".storage/\n.opencontext/\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_smoke.py").write_text(
        "def test_ok() -> None:\n    assert True\n", encoding="utf-8"
    )
    oc = root / ".opencontext"
    oc.mkdir()
    (oc / "sdd").mkdir()
    (oc / "sdd" / "context.json").write_text("{}", encoding="utf-8")
    (oc / "harness.yaml").write_text("version: 0.1\n", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# ChecklistItem
# ---------------------------------------------------------------------------


class TestChecklistItem:
    def test_checklist_item_carries_required_fields(self) -> None:
        item = ChecklistItem(
            key="config",
            label="opencontext.yaml present",
            passed=True,
            weight=10,
            fix_hint="run opencontext init",
        )
        assert item.key == "config"
        assert item.label == "opencontext.yaml present"
        assert item.passed is True
        assert item.weight == 10
        assert item.fix_hint == "run opencontext init"

    def test_checklist_item_weight_defaults_to_one(self) -> None:
        item = ChecklistItem(key="x", label="x", passed=False)
        assert item.weight == 1
        assert item.fix_hint == ""


# ---------------------------------------------------------------------------
# DxChecklist
# ---------------------------------------------------------------------------


class TestDxChecklist:
    def test_empty_checklist_scores_zero(self) -> None:
        checklist = DxChecklist(items=())
        assert checklist.score == 0
        assert checklist.passed == 0
        assert checklist.failed == 0

    def test_all_items_pass_score_100(self) -> None:
        items = (
            ChecklistItem(key="a", label="A", passed=True, weight=2),
            ChecklistItem(key="b", label="B", passed=True, weight=3),
        )
        checklist = DxChecklist(items=items)
        assert checklist.score == 100
        assert checklist.passed == 2
        assert checklist.failed == 0

    def test_weighted_score_handles_partial_credit(self) -> None:
        items = (
            ChecklistItem(key="a", label="A", passed=True, weight=1),
            ChecklistItem(key="b", label="B", passed=False, weight=1),
            ChecklistItem(key="c", label="C", passed=True, weight=2),
        )
        checklist = DxChecklist(items=items)
        # 3 of 4 weighted items pass → 75
        assert checklist.score == 75
        assert checklist.passed == 2
        assert checklist.failed == 1

    def test_score_is_clamped_to_0_100(self) -> None:
        # All items fail → 0, never negative.
        items = (ChecklistItem(key="a", label="A", passed=False, weight=10),)
        checklist = DxChecklist(items=items)
        assert checklist.score == 0

    def test_failing_items_expose_fix_hints(self) -> None:
        items = (
            ChecklistItem(key="a", label="A", passed=False, fix_hint="do X"),
            ChecklistItem(key="b", label="B", passed=True, fix_hint=""),
        )
        checklist = DxChecklist(items=items)
        assert checklist.fix_hints() == ["do X"]

    def test_find_by_key_returns_matching_item(self) -> None:
        items = (
            ChecklistItem(key="a", label="A", passed=True),
            ChecklistItem(key="b", label="B", passed=False),
        )
        checklist = DxChecklist(items=items)
        assert checklist.find("a").label == "A"
        assert checklist.find("missing") is None


# ---------------------------------------------------------------------------
# run_checklist — the live probe
# ---------------------------------------------------------------------------


class TestRunChecklist:
    def test_fresh_project_low_score(self, fresh_project: Path) -> None:
        checklist = run_checklist(fresh_project)
        assert isinstance(checklist, DxChecklist)
        # Nothing present → score must be below the "ready" threshold (80).
        assert checklist.score < 80
        assert checklist.passed < len(checklist.items)

    def test_ready_project_full_score(self, ready_project: Path) -> None:
        checklist = run_checklist(ready_project)
        assert checklist.score >= 80

    def test_returns_same_score_when_called_twice(self, ready_project: Path) -> None:
        a = run_checklist(ready_project)
        b = run_checklist(ready_project)
        assert a.score == b.score

    def test_each_item_key_is_unique(self, ready_project: Path) -> None:
        checklist = run_checklist(ready_project)
        keys = [item.key for item in checklist.items]
        assert len(keys) == len(set(keys))

    def test_checklist_returns_at_least_five_canonical_items(self, ready_project: Path) -> None:
        checklist = run_checklist(ready_project)
        assert len(checklist.items) >= 5

    def test_config_existence_item_passes_when_yaml_present(self, ready_project: Path) -> None:
        checklist = run_checklist(ready_project)
        config_item = checklist.find("config")
        assert config_item is not None
        assert config_item.passed is True

    def test_sdd_context_item_passes_when_context_present(self, ready_project: Path) -> None:
        checklist = run_checklist(ready_project)
        sdd_item = checklist.find("sdd_context")
        assert sdd_item is not None
        assert sdd_item.passed is True

    def test_failing_items_have_fix_hints(self, fresh_project: Path) -> None:
        checklist = run_checklist(fresh_project)
        for item in checklist.items:
            if not item.passed:
                assert item.fix_hint, f"missing fix hint for failed item {item.key!r}"
