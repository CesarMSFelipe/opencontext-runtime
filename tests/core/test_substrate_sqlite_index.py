"""REQ-08: ContextSubstrateBuilder._check_index treats SQLite DB as indexed=True."""

from __future__ import annotations

from pathlib import Path


def test_sqlite_db_triggers_indexed_true(tmp_path: Path) -> None:
    """A temp dir with only .storage/opencontext/context_graph.db → indexed=True."""
    from opencontext_core.agentic.context_substrate import ContextSubstrateBuilder

    db_dir = tmp_path / ".storage" / "opencontext"
    db_dir.mkdir(parents=True)
    (db_dir / "context_graph.db").write_bytes(b"")  # file present, content irrelevant

    builder = ContextSubstrateBuilder(root=tmp_path)
    indexed, status = builder._check_index()

    assert indexed is True
    assert status == "indexed"


def test_no_files_triggers_not_indexed(tmp_path: Path) -> None:
    """Empty temp dir → indexed=False."""
    from opencontext_core.agentic.context_substrate import ContextSubstrateBuilder

    builder = ContextSubstrateBuilder(root=tmp_path)
    indexed, _status = builder._check_index()

    assert indexed is False


def test_legacy_json_still_works(tmp_path: Path) -> None:
    """Legacy .opencontext/knowledge_graph.json still triggers indexed=True."""
    from opencontext_core.agentic.context_substrate import ContextSubstrateBuilder

    oc_dir = tmp_path / ".opencontext"
    oc_dir.mkdir()
    (oc_dir / "knowledge_graph.json").write_text('{"nodes": []}', encoding="utf-8")

    builder = ContextSubstrateBuilder(root=tmp_path)
    indexed, status = builder._check_index()

    assert indexed is True
    assert status == "indexed"
