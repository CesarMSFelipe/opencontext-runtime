"""Tests for openspec/store.py re-export — spec §Domain 6."""

from __future__ import annotations


def test_new_import_path_works() -> None:
    from opencontext_core.openspec.store import OpenSpecStore

    assert OpenSpecStore is not None


def test_same_object_as_original() -> None:
    from opencontext_core.agents.artifact_store import OpenSpecStore as Original
    from opencontext_core.openspec.store import OpenSpecStore as Reexported

    assert Reexported is Original


def test_original_import_still_works() -> None:
    from opencontext_core.agents.artifact_store import OpenSpecStore

    assert OpenSpecStore is not None


def test_openspec_store_is_functional(tmp_path) -> None:
    from opencontext_core.openspec.store import OpenSpecStore

    store = OpenSpecStore(root=str(tmp_path))
    store.save("my-change", "spec", "# Spec content")
    loaded = store.load("my-change", "spec")
    assert loaded == "# Spec content"
