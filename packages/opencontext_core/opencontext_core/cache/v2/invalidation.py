"""Cache v2 — `CacheInvalidationRule` (REQ-cache-v2-003, profile-aware).

Rules fire on file change (mtime / git diff) and may be scoped to a set
of profiles. A rule under the wrong profile is a no-op. Invalidation
emits a `cache.invalidated{reason=…}` event through the optional
``emit`` callable, defaulting to a no-op so the leaf stays import-clean.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field


class CacheInvalidationRule(BaseModel):
    """Profile-aware cache invalidation rule (REQ-cache-v2-003)."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    cache_type: str = Field(description="Cache type this rule applies to (one of the 7).")
    profiles: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Profiles under which this rule fires. Empty = all profiles.",
    )
    on_file_change: bool = Field(
        default=False, description="Fire on file change (mtime / git diff)."
    )
    on_mtime_advance: bool = Field(
        default=True, description="Fire when source mtime advances (default True)."
    )
    reason: str = Field(
        default="file_change", description="Reason string emitted with cache.invalidated."
    )

    def applies_to_profile(self, profile: str) -> bool:
        """Empty profile list = applies to all profiles (default-open)."""
        if not self.profiles:
            return True
        return profile in self.profiles

    def applies_to(self, *, mtime: float | None = None, profile: str = "") -> bool:
        """Decide whether the rule fires for this change."""
        if profile and not self.applies_to_profile(profile):
            return False
        if mtime is not None and not self.on_mtime_advance:
            return False
        return True

    def emit_event(self, *, key: str, source_file: str = "") -> dict[str, str]:
        """Build the `cache.invalidated` event payload (no I/O)."""
        return {
            "rule_id": self.rule_id,
            "cache_type": self.cache_type,
            "reason": self.reason,
            "key": key,
            "source_file": source_file,
        }


EmitFn = Callable[[dict[str, str]], None]


def apply_rule(
    rule: CacheInvalidationRule,
    *,
    matched_keys: list[str],
    source_file: str = "",
    emit: EmitFn | None = None,
) -> int:
    """Apply ``rule`` to ``matched_keys``; return the count invalidated.

    When ``emit`` is provided, each invalidated key produces a
    `cache.invalidated{reason=…}` event payload. Without ``emit`` the
    function stays a pure helper (useful for tests + the leaf).
    """
    count = 0
    for k in matched_keys:
        if emit is not None:
            emit(rule.emit_event(key=k, source_file=source_file))
        count += 1
    return count


__all__ = ["CacheInvalidationRule", "EmitFn", "apply_rule"]
