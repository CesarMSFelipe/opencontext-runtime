"""KG v2 events — PR-008.d."""

from __future__ import annotations


def emit_unknown_owner(path: str) -> dict:
    return {"event": "org.owner.unknown", "path": path, "resolved": False}
