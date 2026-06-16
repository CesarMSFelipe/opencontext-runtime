"""Memory export/import: a git-shareable round-trip that dedups on re-import."""

from __future__ import annotations

from pathlib import Path

from opencontext_cli.main import _memory_export, _memory_import
from opencontext_core.memory_usability.context_repository import ContextRepository


def test_export_import_round_trip(tmp_path: Path) -> None:
    src = ContextRepository(tmp_path / "a")
    src.store(content="We decided to use SQLite for the local store", kind="decision", source="t")
    src.store(content="Authentication lives in src/auth.py", kind="fact", source="t")

    export = tmp_path / "export.json"
    _memory_export(src, str(export))
    assert export.exists()

    dst = ContextRepository(tmp_path / "b")
    _memory_import(dst, str(export))
    items = dst.list_items(include_archive=True)
    assert len(items) == 2
    assert any("SQLite" in i.content for i in items)
    # ids are preserved so a teammate's import keeps stable identity
    assert {i.id for i in items} == {i.id for i in src.list_items(include_archive=True)}


def test_reimport_is_idempotent(tmp_path: Path) -> None:
    src = ContextRepository(tmp_path / "a")
    src.store(content="cache eviction uses LRU policy", kind="fact", source="t")
    export = tmp_path / "export.json"
    _memory_export(src, str(export))

    dst = ContextRepository(tmp_path / "b")
    _memory_import(dst, str(export))
    _memory_import(dst, str(export))  # second time must not duplicate
    assert len(dst.list_items(include_archive=True)) == 1


def test_import_missing_file_exits(tmp_path: Path) -> None:
    dst = ContextRepository(tmp_path / "b")
    try:
        _memory_import(dst, str(tmp_path / "nope.json"))
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected SystemExit on missing file")
