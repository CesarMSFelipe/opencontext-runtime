"""Partial-path incremental name resolution."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
from opencontext_core.indexing.name_resolution import SymbolRef, resolve_partial_path


def _refs() -> list[SymbolRef]:
    return [
        SymbolRef(id="n1", name="login", container="AuthService", file_path="src/auth.py"),
        SymbolRef(id="n2", name="login", container="AdminService", file_path="src/admin.py"),
        SymbolRef(id="n3", name="save", container=None, file_path="src/models.py"),
        SymbolRef(id="n4", name="save", container=None, file_path="src/cache.py"),
        SymbolRef(id="n5", name="unique_fn", container=None, file_path="src/util.py"),
    ]


def test_single_candidate_resolves_without_hints():
    assert resolve_partial_path("unique_fn", _refs()) == "n5"


def test_disambiguates_by_container():
    assert resolve_partial_path("AuthService.login", _refs()) == "n1"
    assert resolve_partial_path("AdminService.login", _refs()) == "n2"


def test_disambiguates_by_file_segment():
    assert resolve_partial_path("models.save", _refs()) == "n3"
    assert resolve_partial_path("cache.save", _refs()) == "n4"


def test_ambiguous_without_useful_hint_returns_none():
    assert resolve_partial_path("login", _refs()) is None  # two logins, no scope
    assert resolve_partial_path("save", _refs()) is None


def test_unknown_name_returns_none():
    assert resolve_partial_path("does_not_exist", _refs()) is None
    assert resolve_partial_path("", _refs()) is None


def test_deeper_path_narrows_incrementally():
    refs = [
        SymbolRef(id="a", name="run", container="Inner", file_path="pkg/one.py"),
        SymbolRef(id="b", name="run", container="Inner", file_path="pkg/two.py"),
    ]
    # Same leaf + same container in two files; the file hint breaks the tie.
    assert resolve_partial_path("one.Inner.run", refs) == "a"
    assert resolve_partial_path("two.Inner.run", refs) == "b"


def test_resolve_symbol_path_through_real_indexed_graph(tmp_path: Path):
    """End-to-end: index two same-named methods, resolve by their class scope."""
    config = KnowledgeGraphConfig(enabled=True, languages=["python"])
    kg = KnowledgeGraph(config=config, db_path=tmp_path / "kg.db")
    try:
        kg.index_file("auth.py", "class AuthService:\n    def login(self):\n        return 1\n")
        kg.index_file("admin.py", "class AdminService:\n    def login(self):\n        return 2\n")

        # Bare "login" is ambiguous across the two classes.
        assert kg.resolve_symbol_path("login") is None
        # Scoped by class, each resolves to the right node.
        auth_id = kg.resolve_symbol_path("AuthService.login")
        admin_id = kg.resolve_symbol_path("AdminService.login")
        assert auth_id is not None and admin_id is not None
        assert auth_id != admin_id

        conn = kg.db._connect()
        auth_file = conn.execute("SELECT file_path FROM nodes WHERE id = ?", (auth_id,)).fetchone()[
            "file_path"
        ]
        assert auth_file == "auth.py"
    finally:
        kg.close()
