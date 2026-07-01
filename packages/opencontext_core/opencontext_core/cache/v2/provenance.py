"""Cache v2 — `Provenance` shared model (PR-000.3, book §5).

Re-exports ``cache.base.CacheProvenance`` as the v2-canonical
``Provenance``. The base model already enforces ``extra='forbid'`` and
carries the four production fields the spec requires:
``producer_run_id``, ``source_hash``, ``captured_at``, ``source_refs``.
"""

from __future__ import annotations

from opencontext_core.cache.base import CacheProvenance as Provenance

__all__ = ["Provenance"]