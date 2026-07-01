"""commit-012: v2 endpoints return the schema promised by the design notes."""

from __future__ import annotations

from typing import Any

import pytest

from opencontext_studio.server_v2 import create_v2_app


@pytest.fixture
def client() -> Any:
    from fastapi.testclient import TestClient

    return TestClient(create_v2_app())


ENDPOINTS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("/api/v2/health", {"status"}),
    ("/api/v2/decision_log/abc-123", {"status", "decision_id", "rationale"}),
    ("/api/v2/brain_state", {"status", "workflow", "persona", "skill", "context"}),
    (
        "/api/v2/capability_graph",
        {"status", "available", "missing", "degraded", "install_hint"},
    ),
    (
        "/api/v2/context_budget",
        {"status", "used_tokens", "available_tokens", "included_refs", "omitted_refs"},
    ),
    (
        "/api/v2/cache_metrics",
        {"status", "hit_rate", "miss_rate", "evictions", "top_keys"},
    ),
    (
        "/api/v2/learning_candidates",
        {"status", "candidates", "evidence", "promotion_status"},
    ),
)


@pytest.mark.parametrize(("path", "expected_keys"), ENDPOINTS)
def test_all_six_return_expected_schema(
    client: Any, path: str, expected_keys: set[str]
) -> None:
    resp = client.get(path)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    missing = expected_keys - body.keys()
    assert not missing, f"missing keys: {missing} in {sorted(body)}"


def test_health_endpoint_returns_200(client: Any) -> None:
    resp = client.get("/api/v2/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "v2"
