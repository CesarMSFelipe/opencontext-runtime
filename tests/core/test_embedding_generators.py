"""create_generator provider routing — including the real local ollama adapter.

The live HTTP path is exercised against a running daemon in manual verification;
here we pin the routing contract and that an unknown provider still fails loudly.
"""

from __future__ import annotations

import pytest

from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.embeddings.generators import (
    DeterministicEmbeddingGenerator,
    OllamaEmbeddingGenerator,
    create_generator,
)


def _config(provider: str, model: str = "nomic-embed-text") -> OpenContextConfig:
    data = default_config_data()
    data["embedding"]["provider"] = provider
    data["embedding"]["model"] = model
    return OpenContextConfig.model_validate(data)


def test_local_provider_routes_to_deterministic() -> None:
    assert isinstance(create_generator(_config("local")), DeterministicEmbeddingGenerator)


def test_ollama_provider_routes_to_ollama_adapter() -> None:
    gen = create_generator(_config("ollama"))
    assert isinstance(gen, OllamaEmbeddingGenerator)
    assert gen.model_name() == "ollama-nomic-embed-text"


def test_unknown_provider_still_raises() -> None:
    with pytest.raises(ValueError, match="Unknown embedding provider"):
        create_generator(_config("definitely-not-a-provider"))


def test_ollama_host_defaults_and_strips_trailing_slash(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://example:1234/")
    gen = OllamaEmbeddingGenerator("nomic-embed-text")
    assert gen._host == "http://example:1234"


def test_null_embedding_worker_is_running_does_not_raise() -> None:
    from opencontext_core.embeddings.worker import NullAsyncEmbeddingWorker

    # __init__ used to skip setting _running, so is_running() raised AttributeError.
    assert NullAsyncEmbeddingWorker().is_running() is False
