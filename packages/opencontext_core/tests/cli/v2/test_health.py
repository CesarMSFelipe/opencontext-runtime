"""REQ-cli-v2-001: health returns short status."""

from __future__ import annotations

from opencontext_cli.commands.v2.health import build_health_summary


def test_REQ_cli_v2_001_short_status() -> None:
    summary = build_health_summary(ok=10, warn=1, fail=0)
    assert summary["ok"] == 10
    assert summary["warn"] == 1
    assert summary["fail"] == 0
    assert summary["status"] in {"ok", "degraded", "down"}


def test_status_ok_when_all_green() -> None:
    assert build_health_summary(ok=5)["status"] == "ok"


def test_status_down_when_failures() -> None:
    assert build_health_summary(ok=5, fail=1)["status"] == "down"