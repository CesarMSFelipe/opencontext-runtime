"""Cache v2 — `CacheProvider` Protocol + L4 leaf base (PR-000.3).

`CacheProvider` is the v2-canonical alias for the doc-59 ``CacheStore``
Protocol. The leaf keeps zero state of its own: producers carry the
keys and provenance; the cache stores them. This file deliberately does
NOT add new abstractions — it re-exports ``CacheStore`` so the v2
namespace reads as the public L4 cache surface.
"""

from __future__ import annotations

from typing import Protocol

from opencontext_core.cache.base import CacheStore


class CacheProvider(CacheStore, Protocol):
    """v2-canonical alias for the doc-59 ``CacheStore`` Protocol."""


__all__ = ["CacheProvider"]