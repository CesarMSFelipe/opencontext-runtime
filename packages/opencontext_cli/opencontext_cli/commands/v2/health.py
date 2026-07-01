"""REQ-cli-v2-001: short health summary."""

from __future__ import annotations

from typing import Any


def build_health_summary(*, ok: int = 0, warn: int = 0, fail: int = 0) -> dict[str, Any]:
    if fail > 0:
        status = "down"
    elif warn > 0:
        status = "degraded"
    else:
        status = "ok"
    return {"ok": ok, "warn": warn, "fail": fail, "status": status}
