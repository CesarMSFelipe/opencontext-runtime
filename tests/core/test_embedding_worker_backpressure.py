"""A full embedding queue is counted as backpressure — not flooded to the console.

Regression guard for the per-item ``embedding queue full, dropping item`` warning
that flooded a first-time ``opencontext init`` (a bulk index enqueues one item per
symbol — more than the generator can drain). Drops must be counted in stats and
stay off the console (debug, not warning).
"""

from __future__ import annotations

import logging

import pytest

from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.embeddings.models import EmbeddedItem
from opencontext_core.embeddings.stores import NullVectorStore
from opencontext_core.embeddings.worker import AsyncEmbeddingWorker


class _StubGenerator:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]

    def model_name(self) -> str:
        return "stub"

    def dimensions(self) -> int:
        return 1


def _item(i: int) -> EmbeddedItem:
    return EmbeddedItem.create(
        item_id=f"n{i}", item_type="symbol", project_name="p", content=f"text {i}"
    )


def test_full_queue_counts_drop_without_warning(caplog: pytest.LogCaptureFixture) -> None:
    config = OpenContextConfig(**default_config_data())
    config.embedding.queue_max_size = 1
    worker = AsyncEmbeddingWorker(
        config, vector_store=NullVectorStore(), generator=_StubGenerator()
    )

    worker._queue.put_nowait(_item(0))  # fill to maxsize=1

    with caplog.at_level(logging.WARNING, logger="opencontext_core.embeddings.worker"):
        worker._enqueue_one(_item(1))  # queue already full → must drop, not warn

    assert worker.stats().dropped_count == 1
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
