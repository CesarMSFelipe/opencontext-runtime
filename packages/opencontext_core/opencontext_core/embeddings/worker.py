"""Async background worker for embedding generation.

Runs embedding generation in a background thread with its own event loop.
Provides a fast synchronous queue operation (<150ms guarantee) to enqueue
items for embedding.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from opencontext_core.config import OpenContextConfig
from opencontext_core.embeddings.generators import create_generator
from opencontext_core.embeddings.models import EmbeddedItem, EmbeddingStats
from opencontext_core.embeddings.protocols import EmbeddingGenerator, VectorStore
from opencontext_core.embeddings.stores import LocalVectorStore

_log = logging.getLogger(__name__)


class AsyncEmbeddingWorker:
    """Background worker for asynchronous embedding generation.

    This worker runs in a separate thread with its own asyncio event loop.
    The synchronous enqueue method completes in <150ms regardless of
    embedding generation time.
    """

    def __init__(
        self,
        config: OpenContextConfig,
        vector_store: VectorStore | None = None,
        generator: EmbeddingGenerator | None = None,
    ) -> None:
        self.config = config
        self.embedding_config = config.embedding

        # Components
        default_path = Path(".storage/opencontext")
        self.vector_store = vector_store or LocalVectorStore(default_path)
        self.generator = generator or create_generator(config)

        # State
        self._queue: asyncio.Queue[EmbeddedItem] = asyncio.Queue(
            maxsize=self.embedding_config.queue_max_size
        )
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        # Stats
        self._stats = EmbeddingStats(
            total_items=0,
            embedded_count=0,
            pending_count=0,
            failed_count=0,
            average_latency_ms=0.0,
            queue_depth=0,
            last_activity=None,
        )
        self._latency_samples: list[float] = []
        self._lock = threading.RLock()

    def start(self) -> None:
        """Start the background worker thread."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_async_loop,
            name="EmbeddingWorker",
            daemon=True,
        )
        self._thread.start()

        # Wait for loop to be ready
        timeout = time.time() + 5.0
        while self._loop is None and time.time() < timeout:
            time.sleep(0.01)

    def stop(self, timeout: float = 10.0) -> None:
        """Stop the background worker gracefully."""
        self._running = False
        if self._thread is not None and self._thread.is_alive():
            # Signal the loop to stop by scheduling stop
            if self._loop is not None:
                asyncio.run_coroutine_threadsafe(self._stop_async(), self._loop)
                self._thread.join(timeout=timeout)
        self._thread = None
        self._loop = None

    async def _stop_async(self) -> None:
        """Async cleanup in the worker loop."""
        self._running = False
        # Cancel pending tasks if needed
        # Let queue drain naturally

    def _run_async_loop(self) -> None:
        """Run asyncio event loop in background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        # Start the worker coroutine.
        self._loop.create_task(self._worker_main())

        try:
            self._loop.run_forever()
        finally:
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.close()

    async def _worker_main(self) -> None:
        """Main worker loop processing embedding batches."""
        batch: list[EmbeddedItem] = []
        batch_timeout = 0.1  # Seconds to wait before processing partial batch
        last_flush = time.time()

        while self._running or not self._queue.empty():
            try:
                # Wait for item with timeout to flush partial batches
                try:
                    item = await asyncio.wait_for(self._queue.get(), timeout=batch_timeout)
                    batch.append(item)
                except TimeoutError:
                    pass  # Timeout reached, process batch if non-empty

                # Check if batch is full or timeout elapsed
                batch_size = len(batch)
                if batch_size >= self.embedding_config.batch_size or (
                    batch and time.time() - last_flush > batch_timeout
                ):
                    await self._process_batch(batch)
                    batch = []
                    last_flush = time.time()

            except Exception as exc:
                # Log error but keep worker alive
                _log.error("embedding worker error: %s", exc)

        # Final flush
        if batch:
            await self._process_batch(batch)

    async def _process_batch(self, batch: list[EmbeddedItem]) -> None:
        """Process a batch of embedding items."""
        if not batch:
            return

        start_time = time.time()

        try:
            # Extract texts
            texts = [item.content for item in batch]

            # Generate embeddings (async)
            vectors = await self.generator.embed(texts)

            # Attach vectors to items
            for item, vector in zip(batch, vectors, strict=False):
                item.vector = vector
                item.embedding_model = self.generator.model_name()
                item.dimensions = self.generator.dimensions()
                item.embedded_at = datetime.now()

            # Store (sync but fast)
            self.vector_store.store(batch)

            # Update stats
            latency_ms = (time.time() - start_time) * 1000
            with self._lock:
                self._stats.embedded_count += len(batch)
                self._stats.total_items += len(batch)
                self._latency_samples.append(latency_ms)
                # Keep only last 100 samples
                if len(self._latency_samples) > 100:
                    self._latency_samples = self._latency_samples[-100:]
                self._stats.average_latency_ms = sum(self._latency_samples) / len(
                    self._latency_samples
                )
                self._stats.last_activity = datetime.now()

        except Exception as exc:
            _log.warning("batch embedding failed: %s", exc)
            with self._lock:
                self._stats.failed_count += len(batch)

    def enqueue_sync(self, items: list[EmbeddedItem]) -> int:
        """Synchronously enqueue items for embedding.

        Guaranteed to complete within 150ms. Does not wait for embedding.

        Args:
            items: Items to embed

        Returns:
            Number of items successfully queued
        """
        start = time.time()
        queued = 0

        for item in items:
            try:
                if not self._running:
                    break
                # Use put_nowait to avoid blocking
                self._queue.put_nowait(item)
                queued += 1
            except asyncio.QueueFull:
                _log.warning("embedding queue full, dropping %d items", len(items) - queued)
                break

        with self._lock:
            self._stats.pending_count = self._queue.qsize()
            self._stats.queue_depth = self._queue.qsize()

        # Verify we're under 150ms
        elapsed = (time.time() - start) * 1000
        if elapsed > 150:
            _log.warning("enqueue took %.1fms, exceeds 150ms guarantee", elapsed)

        return queued

    def stats(self) -> EmbeddingStats:
        """Get current worker statistics."""
        with self._lock:
            # Update dynamic fields
            self._stats.pending_count = self._queue.qsize()
            self._stats.queue_depth = self._queue.qsize()
            return self._stats

    def health(self) -> bool:
        """Check if worker is healthy."""
        return self._running and (self._thread is not None and self._thread.is_alive())

    def is_running(self) -> bool:
        return self._running


def create_worker(
    config: OpenContextConfig,
    vector_store: VectorStore | None = None,
) -> AsyncEmbeddingWorker:
    """Create embedding worker from configuration."""
    if not config.embedding.enabled:
        # Return a null worker that does nothing
        return NullAsyncEmbeddingWorker()

    return AsyncEmbeddingWorker(
        config=config,
        vector_store=vector_store,
    )


class NullAsyncEmbeddingWorker(AsyncEmbeddingWorker):
    """No-op worker for when embeddings are disabled."""

    def __init__(self) -> None:
        # Set the inherited state the no-op overrides don't, so is_running() (which
        # reads self._running) doesn't raise AttributeError.
        self._running = False

    def start(self) -> None:
        pass

    def stop(self, timeout: float = 10.0) -> None:
        pass

    def enqueue_sync(self, items: list[EmbeddedItem]) -> int:
        return len(items)

    def stats(self) -> EmbeddingStats:
        return EmbeddingStats(
            total_items=0,
            embedded_count=0,
            pending_count=0,
            failed_count=0,
            average_latency_ms=0.0,
            queue_depth=0,
            last_activity=None,
        )

    def health(self) -> bool:
        return True
