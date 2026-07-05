"""commit-013: consolidated real-state gate (Amendment-2 / DoD #12).

Each of the 12 TUI screens MUST display the real public-contract fields
listed in the design — never placeholders, never empty bodies. The
parametrized test below iterates the registry and asserts the
required keys are present in each screen's rendered output.
"""

from __future__ import annotations

import pytest
from opencontext_studio.tui.screens import SCREENS

REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "dashboard": ("project", "session_id", "run_id", "gates", "next_action"),
    "workflows": ("workflow", "alternatives", "confidence", "risk"),
    "decision_log": ("decision_id", "rationale", "alternatives", "cost", "timestamp"),
    "brain_scheduler": (
        "workflow_decision",
        "persona_decision",
        "skill_decision",
        "context_decision",
    ),
    "capability_graph": ("available", "missing", "degraded", "install_hint"),
    "context_budget": ("used_tokens", "available_tokens", "included_refs", "omitted_refs"),
    "cache_metrics": ("hit_rate", "miss_rate", "evictions", "top_keys"),
    "learning_candidates": ("candidates", "evidence", "promotion_status"),
    "plugin_panel": ("installed", "capabilities", "policy_status"),
    "provider_health": ("provider", "status", "latency_p50", "latency_p95", "error_rate"),
    "benchmark_status": tuple(f"suite-{i:02d}" for i in range(1, 13)),
    "settings": ("profile", "config_path", "scope", "strict_tdd", "redaction"),
}


@pytest.mark.parametrize("screen_id", sorted(REQUIRED_FIELDS))
def test_screen_renders_real_state(screen_id: str) -> None:
    factory = SCREENS[screen_id]
    screen = factory()
    body = screen.rendered
    assert body and body.strip(), f"{screen_id} rendered an empty body"
    missing = [k for k in REQUIRED_FIELDS[screen_id] if k not in body]
    assert not missing, f"{screen_id} missing keys {missing} in rendered body: {body!r}"


def test_all_twelve_screens_registered() -> None:
    assert len(SCREENS) == 12, f"expected 12 screens, got {len(SCREENS)}: {sorted(SCREENS)}"
