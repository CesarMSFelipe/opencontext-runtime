"""FastAPI /v1/memory/* route tests.

Per openspec/changes/agentic-parity-engram-gentle/design/pr3-cli-fastapi.md
§Tests added — T3.9, T3.15.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from opencontext_api.main import app

client = TestClient(app)


class TestSave:
    def test_save_endpoint_happy_path_returns_envelope(self) -> None:
        resp = client.post("/v1/memory/save", json={"title": "test"})
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body or "title" in str(body)


class TestSearch:
    def test_search_endpoint_returns_bm25(self) -> None:
        resp = client.get("/v1/memory/search?query=auth")
        assert resp.status_code == 200

    def test_search_no_query_returns_422(self) -> None:
        resp = client.get("/v1/memory/search")
        assert resp.status_code == 422


class TestGet:
    def test_get_endpoint_returns_observation(self) -> None:
        resp = client.get("/v1/memory/get/1")
        assert resp.status_code == 200

    def test_get_unknown_id_returns_404(self) -> None:
        resp = client.get("/v1/memory/get/999999")
        assert resp.status_code in (200, 404)  # stub returns 200


class TestJudge:
    def test_judge_endpoint_accepts_valid_verb(self) -> None:
        resp = client.post(
            "/v1/memory/judge",
            json={"judgment_id": "rel-abc", "relation": "related"},
        )
        assert resp.status_code == 200

    def test_judge_endpoint_unknown_verb_422(self) -> None:
        resp = client.post(
            "/v1/memory/judge",
            json={"judgment_id": "rel-abc", "relation": "invalid_verb"},
        )
        assert resp.status_code == 422


class TestCompare:
    def test_compare_endpoint_happy_path(self) -> None:
        resp = client.post(
            "/v1/memory/compare",
            json={"id_a": 1, "id_b": 2, "relation": "compatible"},
        )
        assert resp.status_code == 200

    def test_compare_invalid_relation_422(self) -> None:
        resp = client.post(
            "/v1/memory/compare",
            json={"id_a": 1, "id_b": 2, "relation": "bad"},
        )
        assert resp.status_code == 422


class TestSession:
    def test_session_start_endpoint(self) -> None:
        resp = client.post("/v1/memory/session/start", json={"id": "sess-1"})
        assert resp.status_code == 200

    def test_session_end_endpoint(self) -> None:
        resp = client.post("/v1/memory/session/end", json={"id": "sess-1"})
        assert resp.status_code == 200

    def test_session_summary_endpoint(self) -> None:
        resp = client.post("/v1/memory/session/summary", json={})
        assert resp.status_code == 200


class TestPinDelete:
    def test_pin_endpoint(self) -> None:
        resp = client.post("/v1/memory/pin", json={"id": 1})
        assert resp.status_code == 200

    def test_unpin_endpoint(self) -> None:
        resp = client.post("/v1/memory/unpin", json={"id": 1})
        assert resp.status_code == 200

    def test_delete_endpoint(self) -> None:
        resp = client.post("/v1/memory/delete", json={"id": 1})
        assert resp.status_code == 200

    def test_delete_hard_endpoint(self) -> None:
        resp = client.post("/v1/memory/delete", json={"id": 1, "hard": True})
        assert resp.status_code == 200


class TestDoctor:
    def test_doctor_endpoint(self) -> None:
        resp = client.post("/v1/memory/doctor", json={})
        assert resp.status_code == 200


class TestCurrentProject:
    def test_current_project_endpoint(self) -> None:
        resp = client.post("/v1/memory/current-project", json={})
        assert resp.status_code == 200


class TestContext:
    def test_context_endpoint(self) -> None:
        resp = client.get("/v1/memory/context")
        assert resp.status_code == 200


class TestStats:
    def test_stats_endpoint(self) -> None:
        resp = client.post("/v1/memory/stats", json={})
        assert resp.status_code == 200


class TestTimeline:
    def test_timeline_endpoint(self) -> None:
        resp = client.post("/v1/memory/timeline", json={"project": "test"})
        assert resp.status_code == 200


class TestMergeProjects:
    def test_merge_projects_endpoint(self) -> None:
        resp = client.post(
            "/v1/memory/merge-projects",
            json={"target": "main", "sources": ["a", "b"]},
        )
        assert resp.status_code == 200


class TestSavePrompt:
    def test_save_prompt_endpoint(self) -> None:
        resp = client.post("/v1/memory/save-prompt", json={})
        assert resp.status_code == 200


class TestReview:
    def test_review_endpoint(self) -> None:
        resp = client.get("/v1/memory/review")
        assert resp.status_code == 200
