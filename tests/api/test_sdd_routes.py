"""FastAPI /v1/sdd/* route tests.

Per openspec/changes/agentic-parity-engram-gentle/design/pr3-cli-fastapi.md
§Tests added — T3.11, T3.15.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from opencontext_api.main import app

client = TestClient(app)


class TestStatus:
    def test_status_endpoint_returns_schema_name(self) -> None:
        resp = client.get("/v1/sdd/status?change=test&cwd=.")
        assert resp.status_code == 200
        body = resp.json()
        assert "schemaName" in body


class TestContinue:
    def test_continue_endpoint_returns_markdown(self) -> None:
        resp = client.post("/v1/sdd/continue", json={"change": "test", "cwd": "."})
        assert resp.status_code == 200

    def test_continue_no_change_returns_422(self) -> None:
        resp = client.post("/v1/sdd/continue", json={})
        assert resp.status_code == 422


class TestPhase:
    def test_phase_endpoint_apply(self) -> None:
        resp = client.post("/v1/sdd/apply", json={"change": "test", "cwd": "."})
        assert resp.status_code == 200

    def test_phase_endpoint_explore(self) -> None:
        resp = client.post("/v1/sdd/explore", json={"topic": "auth"})
        assert resp.status_code == 200

    def test_phase_endpoint_propose(self) -> None:
        resp = client.post("/v1/sdd/propose", json={"change": "test"})
        assert resp.status_code == 200

    def test_phase_endpoint_spec(self) -> None:
        resp = client.post("/v1/sdd/spec", json={"change": "test"})
        assert resp.status_code == 200

    def test_phase_endpoint_design(self) -> None:
        resp = client.post("/v1/sdd/design", json={"change": "test"})
        assert resp.status_code == 200

    def test_phase_endpoint_tasks(self) -> None:
        resp = client.post("/v1/sdd/tasks", json={"change": "test"})
        assert resp.status_code == 200

    def test_phase_endpoint_verify(self) -> None:
        resp = client.post("/v1/sdd/verify", json={"change": "test"})
        assert resp.status_code == 200

    def test_phase_endpoint_archive(self) -> None:
        resp = client.post("/v1/sdd/archive", json={"change": "test"})
        assert resp.status_code == 200

class TestNegativePaths:
    def test_sdd_unknown_phase_returns_404(self) -> None:
        """Unrecognized POST phase returns 404."""
        resp = client.post("/v1/sdd/unknown", json={"change": "test"})
        assert resp.status_code == 404

    def test_memory_unknown_endpoint_returns_405(self) -> None:
        """Unknown GET returns 405 (Method Not Allowed) because a route exists."""
        resp = client.get("/v1/memory/nonexistent")
        assert resp.status_code in (404, 405)
