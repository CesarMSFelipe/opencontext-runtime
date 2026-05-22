"""Memory management for agents."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional


@dataclass
class MemoryEntry:
    """Single memory entry."""

    key: str
    value: Any
    created_at: datetime = field(default_factory=datetime.now)
    accessed_at: datetime = field(default_factory=datetime.now)
    ttl_minutes: Optional[int] = None

    @property
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.ttl_minutes is None:
            return False
        expiry = self.created_at + timedelta(minutes=self.ttl_minutes)
        return datetime.now() > expiry

    def touch(self) -> None:
        """Update access time."""
        self.accessed_at = datetime.now()


class MemoryManager:
    """Manages agent memory with TTL and eviction."""

    def __init__(self, max_entries: int = 100, ttl_minutes: Optional[int] = None):
        """Initialize memory manager.

        Args:
            max_entries: Maximum entries before LRU eviction
            ttl_minutes: Default TTL for entries (None = indefinite)
        """
        self.max_entries = max_entries
        self.ttl_minutes = ttl_minutes
        self.store: dict[str, MemoryEntry] = {}

    def set(self, key: str, value: Any, ttl_minutes: Optional[int] = None) -> None:
        """Store value in memory.

        Args:
            key: Memory key
            value: Value to store
            ttl_minutes: Optional TTL override
        """
        ttl = ttl_minutes or self.ttl_minutes
        self.store[key] = MemoryEntry(key=key, value=value, ttl_minutes=ttl)

        # Evict if over limit
        if len(self.store) > self.max_entries:
            self._evict_lru()

    def get(self, key: str) -> Optional[Any]:
        """Retrieve value from memory.

        Args:
            key: Memory key

        Returns:
            Value or None if not found or expired
        """
        entry = self.store.get(key)
        if entry is None:
            return None

        if entry.is_expired:
            del self.store[key]
            return None

        entry.touch()
        return entry.value

    def delete(self, key: str) -> None:
        """Delete memory entry.

        Args:
            key: Memory key to delete
        """
        self.store.pop(key, None)

    def clear(self) -> None:
        """Clear all memory."""
        self.store.clear()

    def _evict_lru(self) -> None:
        """Evict least recently used entry."""
        if not self.store:
            return

        lru_key = min(
            self.store.keys(),
            key=lambda k: self.store[k].accessed_at,
        )
        del self.store[lru_key]

    def cleanup_expired(self) -> int:
        """Remove all expired entries.

        Returns:
            Number of entries cleaned
        """
        expired_keys = [
            k for k, v in self.store.items() if v.is_expired
        ]
        for key in expired_keys:
            del self.store[key]
        return len(expired_keys)

    @property
    def size(self) -> int:
        """Get current memory size."""
        return len(self.store)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "max_entries": self.max_entries,
            "current_size": self.size,
            "entries": {
                k: {
                    "created_at": v.created_at.isoformat(),
                    "accessed_at": v.accessed_at.isoformat(),
                    "ttl_minutes": v.ttl_minutes,
                }
                for k, v in self.store.items()
            },
        }
