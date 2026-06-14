"""Tests for stable symbol IDs and global_map collision fix in knowledge_graph."""

from opencontext_core.indexing.knowledge_graph import _stable_symbol_id


def test_same_name_different_files_different_ids():
    id1 = _stable_symbol_id("proj", "auth.py", "validate", "function")
    id2 = _stable_symbol_id("proj", "utils.py", "validate", "function")
    assert id1 != id2


def test_same_symbol_same_file_deterministic():
    id1 = _stable_symbol_id("proj", "auth.py", "validate", "function")
    id2 = _stable_symbol_id("proj", "auth.py", "validate", "function")
    assert id1 == id2


def test_stable_symbol_id_is_deterministic_across_calls():
    results = [_stable_symbol_id("p", "f.py", "MyClass.method", "method") for _ in range(5)]
    assert len(set(results)) == 1


def test_stable_symbol_id_length():
    sid = _stable_symbol_id("proj", "auth.py", "validate", "function")
    assert len(sid) == 16
