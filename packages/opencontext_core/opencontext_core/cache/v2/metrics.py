"""Cache v2 — `CacheMetrics` (REQ-cache-v2-004).

Per-type hit/miss counters + an `emit` hook for `cache.hit` / `cache.miss`
events. The CLI surface (``opencontext cache stats``) reads
``cache_stats_payload``; the Studio cache view reads the same payload
through PR-014's port.
"""

from __future__ import annotations

from collections.abc import Callable

EmitFamilyFn = Callable[[str, str], None]


class CacheMetrics:
    """Per-cache-type hit/miss counters with optional event emission."""

    def __init__(self, *, emit: EmitFamilyFn | None = None) -> None:
        self._counts: dict[str, dict[str, int]] = {}
        self._emit = emit

    def record_hit(self, cache_type: str) -> None:
        self._counts.setdefault(cache_type, {"hits": 0, "misses": 0})["hits"] += 1
        if self._emit is not None:
            self._emit("cache.hit", cache_type)

    def record_miss(self, cache_type: str) -> None:
        self._counts.setdefault(cache_type, {"hits": 0, "misses": 0})["misses"] += 1
        if self._emit is not None:
            self._emit("cache.miss", cache_type)

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        """Return per-type counters + hit_rate."""
        out: dict[str, dict[str, float | int]] = {}
        for cache_type, counts in sorted(self._counts.items()):
            hits = counts["hits"]
            misses = counts["misses"]
            total = hits + misses
            out[cache_type] = {
                "hits": hits,
                "misses": misses,
                "total": total,
                "hit_rate": (hits / total) if total > 0 else 0.0,
            }
        return out

    def overall_hit_rate(self) -> float:
        total_hits = sum(c["hits"] for c in self._counts.values())
        total_misses = sum(c["misses"] for c in self._counts.values())
        total = total_hits + total_misses
        return (total_hits / total) if total > 0 else 0.0


def cache_stats_payload(metrics: CacheMetrics) -> dict[str, object]:
    """Stable CLI/Studio payload for `opencontext cache stats` (REQ-cache-v2-004)."""
    snap = metrics.snapshot()
    hits = sum(int(v["hits"]) for v in snap.values())
    misses = sum(int(v["misses"]) for v in snap.values())
    total = hits + misses
    return {
        "hits": hits,
        "misses": misses,
        "total": total,
        "hit_rate": (hits / total) if total > 0 else 0.0,
        "by_type": snap,
    }


__all__ = ["CacheMetrics", "EmitFamilyFn", "cache_stats_payload"]
