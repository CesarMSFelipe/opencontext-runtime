"""Tests for vector backends."""

import pytest

from opencontext_core.backends.vector.local import LocalVectorBackend
from opencontext_core.backends.vector.null import NullVectorBackend
from opencontext_core.exceptions import BackendUnavailableError


def test_semantic_vector_backend_raises_backend_unavailable_not_import_error():
    with pytest.raises(BackendUnavailableError):
        from opencontext_core.backends.vector.semantic import SemanticVectorBackend

        SemanticVectorBackend()


def test_semantic_vector_backend_error_contains_feature_name():
    with pytest.raises(BackendUnavailableError) as exc_info:
        from opencontext_core.backends.vector.semantic import SemanticVectorBackend

        SemanticVectorBackend()
    assert "semantic-search" in str(exc_info.value)


def test_semantic_error_no_tech_name():
    with pytest.raises(BackendUnavailableError) as exc_info:
        from opencontext_core.backends.vector.semantic import SemanticVectorBackend

        SemanticVectorBackend()
    msg = str(exc_info.value).lower()
    assert "qdrant" not in msg


def test_null_vector_backend_search_returns_empty_list():
    backend = NullVectorBackend()
    result = backend.search([0.1, 0.2, 0.3], top_k=5, filter=None)
    assert result == []


def test_local_vector_backend_store_and_search():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        backend = LocalVectorBackend(Path(tmpdir))
        backend.store("item1", [1.0, 0.0, 0.0], {"label": "a"})
        backend.store("item2", [0.0, 1.0, 0.0], {"label": "b"})
        results = backend.search([1.0, 0.0, 0.0], top_k=1, filter=None)
        assert len(results) == 1
        assert results[0]["item_id"] == "item1"
