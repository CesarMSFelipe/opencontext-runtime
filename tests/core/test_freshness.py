"""Index freshness: detect files that changed or were deleted since indexing."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.indexing.knowledge_graph import KnowledgeGraph


def _kg(tmp_path: Path) -> KnowledgeGraph:
    return KnowledgeGraph(db_path=tmp_path / ".storage" / "cg.db")


def test_detects_changed_and_deleted(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def f():\n    return 0\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def g():\n    return 1\n", encoding="utf-8")
    kg = _kg(tmp_path)
    kg.index_file("a.py", (tmp_path / "a.py").read_text())
    kg.index_file("b.py", (tmp_path / "b.py").read_text())

    assert kg.stale_files(tmp_path).total == 0  # just indexed -> fresh

    (tmp_path / "a.py").write_text("def f():\n    return 999\n", encoding="utf-8")
    (tmp_path / "b.py").unlink()
    report = kg.stale_files(tmp_path)
    assert report.changed == ["a.py"]
    assert report.deleted == ["b.py"]

    # Reindexing the changed file clears it; the deleted one stays flagged.
    kg.index_file("a.py", (tmp_path / "a.py").read_text())
    report2 = kg.stale_files(tmp_path)
    assert report2.changed == []
    assert report2.deleted == ["b.py"]
    kg.close()


def test_fresh_when_unchanged(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("X = 1\n", encoding="utf-8")
    kg = _kg(tmp_path)
    kg.index_file("m.py", (tmp_path / "m.py").read_text())
    assert kg.stale_files(tmp_path).total == 0
    kg.close()
