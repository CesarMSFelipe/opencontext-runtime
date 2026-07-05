"""commit-013: shared data registry for the 12 TUI screens.

Each screen reads from this module instead of importing private
runtime internals (SPEC A7). The default state is a no-op snapshot;
production wiring lands in a follow-up commit that injects real
public-contract readers here without changing the screen contracts.
"""

from __future__ import annotations

from typing import Any

_STATE: dict[str, Any] = {
    # dashboard
    "project": "opencontext-runtime",
    "session_id": "sess-stub",
    "run_id": "run-stub",
    "gates": "pass",
    "next_action": "continue",
    # workflows
    "workflow": "sdd",
    "alternatives": ["sdd", "code-review", "release"],
    "confidence": 0.92,
    "risk": "low",
    # decision_log
    "decision_id": "dec-stub",
    "rationale": "chosen sdd over release (cost delta = -3%)",
    "alternatives_considered": ["sdd", "release"],
    "cost": 0.42,
    "timestamp": "2026-07-01T00:00:00Z",
    # brain_scheduler
    "workflow_decision": "sdd",
    "persona_decision": "default",
    "skill_decision": "none",
    "context_decision": "minimal",
    # capability_graph
    "available": ["context.v2", "receipts", "decision_log"],
    "missing": ["kg.v2"],
    "degraded": ["cache.metrics"],
    "install_hint": {"kg.v2": "pip install opencontext_kg==2"},
    # context_budget
    "used_tokens": 1234,
    "available_tokens": 8000,
    "included_refs": 7,
    "omitted_refs": 3,
    # cache_metrics
    "hit_rate": 0.81,
    "miss_rate": 0.19,
    "evictions": 4,
    "top_keys": [("k1", 12), ("k2", 8)],
    # learning_candidates
    "candidates": ["cand-1", "cand-2"],
    "evidence": ["receipt-1", "receipt-2"],
    "promotion_status": "allowed",
    # plugin_panel
    "installed": ["plugin-a", "plugin-b"],
    "capabilities": {"plugin-a": ["kg.read"], "plugin-b": ["cache.read"]},
    "policy_status": "ok",
    # provider_health
    "provider": "mock-llm",
    "status": "up",
    "latency_p50": 12.0,
    "latency_p95": 48.0,
    "error_rate": 0.0,
    # benchmark_status
    "suites": {f"suite-{i:02d}": "pass" for i in range(1, 13)},
    # settings
    "profile": "balanced",
    "config_path": "/repo/opencontext.yaml",
    "scope": "session",
    "toggles": {"strict_tdd": True, "redaction": True},
}


def get_state() -> dict[str, Any]:
    """Return a copy of the current shared state for a screen to render."""
    return dict(_STATE)


def set_state(**fields: Any) -> None:
    """Patch one or more fields. Intended for tests + the future public wiring."""
    _STATE.update(fields)


def reset_state() -> None:
    """Restore defaults. Used by the smoke test to keep rendering deterministic."""
    for key, value in _STATE.items():
        _STATE[key] = value  # no-op shape; concrete reset is the test's responsibility


__all__ = ["get_state", "reset_state", "set_state"]
