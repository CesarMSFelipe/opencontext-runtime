"""Git working-set seeding: candidates from recently-changed files get boosted."""

from __future__ import annotations

from opencontext_core.models.context import ContextItem, ContextPriority
from opencontext_core.retrieval.planner import _git_focus_files, _personalization_map


def _item(item_id: str, source: str) -> ContextItem:
    return ContextItem(
        id=item_id,
        source=source,
        source_type="graph_symbol",
        content=f"def {item_id}(): ...",
        priority=ContextPriority.P1,
        tokens=10,
        score=0.5,
    )


def test_focus_files_boost_changed_file_candidate():
    a = _item("a", "src/auth.py:1:a")
    b = _item("b", "src/other.py:1:b")
    items = [a, b]

    # No query terms and no focus -> no seeds -> the two are not separated by PPR.
    flat = _personalization_map(items, "")
    assert flat["a"] == flat["b"]

    # Seeding the file 'a' came from lifts 'a' above 'b' without any query match.
    focused = _personalization_map(items, "", frozenset({"src/auth.py"}))
    assert focused["a"] > focused["b"]


def test_git_focus_files_is_safe_outside_a_repo(tmp_path):
    # A non-repo path must yield an empty set, never raise.
    assert _git_focus_files(tmp_path) == frozenset()
    assert _git_focus_files(None) == frozenset()
