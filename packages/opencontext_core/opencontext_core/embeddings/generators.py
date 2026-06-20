"""Embedding generation with provider abstraction."""

from __future__ import annotations

import hashlib
import math
from typing import Any

from opencontext_core.config import OpenContextConfig
from opencontext_core.embeddings.protocols import EmbeddingGenerator


class DeterministicEmbeddingGenerator(EmbeddingGenerator):
    """Deterministic embedding generator using seeded random from text hash.

    Produces consistent vectors without external API calls.uitable for
    development, testing, and air-gapped deployments.

    The vector is derived from SHA256 hash of the text, expanded to the
    requested dimensions using a PRNG with a fixed seed per text.
    """

    def __init__(self, dimensions: int = 1536, seed: int = 42) -> None:
        self._dimensions = dimensions
        self._base_seed = seed

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate deterministic embeddings for texts."""
        import asyncio

        # Simulate some async I/O delay for realistic batching behavior
        await asyncio.sleep(0)  # yield to event loop

        vectors = []
        for text in texts:
            # Create a seed from text hash + base seed
            text_hash = hashlib.sha256(text.encode("utf-8")).digest()
            hash_int = int.from_bytes(text_hash[:8], "big", signed=False)
            seed = (hash_int + self._base_seed) % (2**32)

            # Generate deterministic pseudo-random vector
            rng = deterministic_rng(seed)
            vector = [rng() for _ in range(self._dimensions)]

            # Normalize to unit length (cosine similarity ready)
            magnitude = math.sqrt(sum(v * v for v in vector))
            if magnitude > 0:
                vector = [v / magnitude for v in vector]

            vectors.append(vector)
        return vectors

    def dimensions(self) -> int:
        return self._dimensions

    def model_name(self) -> str:
        return f"deterministic-{self._dimensions}d"


def deterministic_rng(seed: int) -> Any:
    """Simple deterministic RNG returning callable that yields floats in [0,1)."""
    state = seed

    def next_float() -> float:
        nonlocal state
        # Xorshift-like PRNG
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= (state >> 17) & 0xFFFFFFFF
        state ^= (state << 5) & 0xFFFFFFFF
        # Convert to float in [0, 1)
        return (state % 1000000) / 1000000.0

    return next_float


class OllamaEmbeddingGenerator(EmbeddingGenerator):
    """Real local embeddings via a co-resident Ollama daemon (no external API).

    Calls ``POST {host}/api/embeddings`` once per text with the configured model
    (e.g. ``nomic-embed-text``). The host defaults to ``$OLLAMA_HOST`` or
    ``http://localhost:11434``. ``dimensions()`` reflects the model's real vector
    width once the first embedding is seen, falling back to the configured value.
    """

    def __init__(self, model: str, *, dimensions: int = 768, host: str | None = None) -> None:
        import os

        self._model = model
        self._dimensions = dimensions
        self._host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        return [await asyncio.to_thread(self._embed_one, text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        import json
        import urllib.request

        payload = json.dumps({"model": self._model, "prompt": text}).encode("utf-8")
        req = urllib.request.Request(
            f"{self._host}/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            vector = json.loads(resp.read()).get("embedding") or []
        if vector:
            self._dimensions = len(vector)
        return [float(v) for v in vector]

    def dimensions(self) -> int:
        return self._dimensions

    def model_name(self) -> str:
        return f"ollama-{self._model}"


class MockEmbeddingGenerator(EmbeddingGenerator):
    """Mock generator that returns zero vectors (for unit tests)."""

    def __init__(self, dimensions: int = 1536) -> None:
        self._dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return zero vectors."""
        return [[0.0] * self._dimensions for _ in texts]

    def dimensions(self) -> int:
        return self._dimensions

    def model_name(self) -> str:
        return f"mock-{self._dimensions}d"


def create_generator(config: OpenContextConfig) -> EmbeddingGenerator:
    """Create embedding generator from configuration."""
    provider = getattr(config.embedding, "provider", "local")
    dimensions = getattr(config.embedding, "dimensions", 1536)

    if provider in ("local", "deterministic"):
        return DeterministicEmbeddingGenerator(dimensions=dimensions)
    elif provider == "mock":
        return MockEmbeddingGenerator(dimensions=dimensions)
    elif provider == "ollama":
        model = getattr(config.embedding, "model", "nomic-embed-text")
        return OllamaEmbeddingGenerator(model=model, dimensions=dimensions)
    else:
        # External providers require adapter packages outside core.
        raise ValueError(
            f"Unknown embedding provider '{provider}'. "
            f"Install the appropriate provider adapter package."
        )
