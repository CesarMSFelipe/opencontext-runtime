"""Proactive save triggers for automatic memory persistence.

Provides hooks and conditions for automatically saving observations
to persistent memory after significant events.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar


class SaveTrigger(Enum):
    """Types of events that trigger proactive saves."""

    ARCHITECTURE_DECISION = "architecture_decision"
    BUG_FIX = "bug_fix"
    CONVENTION_ESTABLISHED = "convention_established"
    TOOL_CHOICE = "tool_choice"
    CONFIG_CHANGE = "config_change"
    DISCOVERY = "discovery"
    PATTERN_ESTABLISHED = "pattern_established"
    USER_PREFERENCE = "user_preference"


@dataclass
class ProactiveSaveEvent:
    """An event that triggered a proactive save."""

    trigger: SaveTrigger
    title: str
    content: str
    project: str


class ProactiveSaveHooks:
    """Hooks for proactive memory saves.

    After every significant task, call `check_and_trigger()` to
    determine if a proactive save should occur.
    """

    TRIGGER_PATTERNS: ClassVar[dict[SaveTrigger, list[str]]] = {
        SaveTrigger.ARCHITECTURE_DECISION: [
            "decision", "architecture", "design", "approach",
            "pattern", "refactor", "restructure",
        ],
        SaveTrigger.BUG_FIX: [
            "fix", "bug", "error", "crash", "resolve", "patch",
        ],
        SaveTrigger.CONVENTION_ESTABLISHED: [
            "convention", "standard", "guideline", "rule", "policy",
        ],
        SaveTrigger.TOOL_CHOICE: [
            "tool", "library", "package", "dependency", "framework",
        ],
        SaveTrigger.CONFIG_CHANGE: [
            "config", "configuration", "setting", "env", "yaml",
        ],
        SaveTrigger.DISCOVERY: [
            "discover", "learn", "found", "realize", "understand",
        ],
        SaveTrigger.PATTERN_ESTABLISHED: [
            "pattern", "idiom", "practice", "habit", "workflow",
        ],
        SaveTrigger.USER_PREFERENCE: [
            "prefer", "want", "like", "dislike", "style",
        ],
    }

    def should_save(
        self,
        title: str,
        content: str,
    ) -> list[SaveTrigger]:
        """Check if the given title/content should trigger a proactive save.

        Args:
            title: Event title.
            content: Event content.

        Returns:
            List of matching trigger types.
        """

        text = f"{title} {content}".lower()
        matched: list[SaveTrigger] = []

        for trigger, keywords in self.TRIGGER_PATTERNS.items():
            if any(kw in text for kw in keywords):
                matched.append(trigger)

        return matched

    def create_event(
        self,
        trigger: SaveTrigger,
        title: str,
        content: str,
        project: str,
    ) -> ProactiveSaveEvent:
        """Create a proactive save event."""

        return ProactiveSaveEvent(
            trigger=trigger,
            title=title,
            content=content,
            project=project,
        )
