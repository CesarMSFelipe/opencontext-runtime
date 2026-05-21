"""Topic key management for stable artifact identifiers in memory."""

from __future__ import annotations

import re


def generate_topic_key(title: str, content: str | None = None) -> str:
    """Generate a stable topic key from a title or content.

    Topic keys enable upsert semantics: same key + project + scope
    updates rather than duplicates.

    Args:
        title: Human-readable title.
        content: Optional content for fallback.

    Returns:
        Normalized topic key string.
    """

    # Use title if available, otherwise content
    source = title if title else (content or "unknown")

    # Lowercase, replace spaces with hyphens
    key = source.lower().strip()

    # Remove non-alphanumeric except hyphens and slashes
    key = re.sub(r"[^a-z0-9/\-]", "-", key)

    # Collapse multiple hyphens
    key = re.sub(r"-+", "-", key)

    # Trim leading/trailing hyphens
    key = key.strip("-")

    # Limit length
    if len(key) > 80:
        key = key[:80]

    return key


def suggest_topic_key(
    title: str | None = None,
    content: str | None = None,
    artifact_type: str | None = None,
) -> str:
    """Suggest a stable topic key for an observation.

    Prefers title, falls back to content, optionally prefixes with artifact type.

    Args:
        title: Observation title.
        content: Observation content (fallback).
        artifact_type: Type of artifact (e.g., "architecture", "bugfix").

    Returns:
        Suggested topic key.
    """

    key = generate_topic_key(title or "", content)

    if artifact_type:
        prefix = artifact_type.lower().replace(" ", "-")
        key = f"{prefix}/{key}"

    return key
