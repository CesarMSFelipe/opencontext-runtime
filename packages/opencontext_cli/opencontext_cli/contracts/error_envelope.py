"""Standard JSON envelopes for machine-facing CLI output."""

from __future__ import annotations

from typing import Any


def error_envelope(
    code: str,
    message: str,
    *,
    hint: str | None = None,
    details: dict[str, Any] | None = None,
    status: str = "failed",
) -> dict[str, Any]:
    """Standard error payload: ``{"ok": false, "status": ..., "error": {...}}``."""
    error: dict[str, Any] = {"code": code, "message": message}
    if hint is not None:
        error["hint"] = hint
    if details is not None:
        error["details"] = details
    return {"ok": False, "status": status, "error": error}


def success_envelope(data: dict[str, Any], *, status: str = "passed") -> dict[str, Any]:
    """Standard success payload: ``{"ok": true, "status": ..., **data}``."""
    return {"ok": True, "status": status, **data}
