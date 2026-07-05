from __future__ import annotations

from typing import Any

"""KG v2 events — PR-008.d."""


def emit_unknown_owner(path: str) -> dict[Any, Any]:
    return {"event": "org.owner.unknown", "path": path, "resolved": False}
