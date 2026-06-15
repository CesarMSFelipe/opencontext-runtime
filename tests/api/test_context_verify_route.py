"""the HTTP API must expose the gated verify_context pipeline.

Before the fix the API shipped VerifiedContextResponse but wired NO endpoint to
verify_context — only the ungated /v1/context/pack and /v1/context existed, so the
'verified' guarantee was CLI-only. This pins the /v1/context/verify route.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from opencontext_core.config import default_config_data
from opencontext_core.runtime import OpenContextRuntime


def _create_sample_project(root: Path) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "auth.py").write_text(
        "class AuthService:\n"
        "    def login(self, username: str) -> bool:\n"
        "        return bool(username)\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# Sample\nAuthentication lives in src/auth.py\n", encoding="utf-8"
    )


def _runtime_factory(tmp_path: Path, project_root: Path):
    data = default_config_data()
    data["project"]["name"] = "api-verify-test"
    data["project_index"]["root"] = str(project_root)
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    def factory() -> OpenContextRuntime:
        return OpenContextRuntime(
            config_path=config_path, storage_path=tmp_path / ".storage/opencontext"
        )

    return factory


def test_api_verify_context_returns_gates_and_loadable_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    import opencontext_api.main as api_main

    project_root = tmp_path / "project"
    project_root.mkdir()
    _create_sample_project(project_root)
    monkeypatch.setattr(api_main, "_runtime", _runtime_factory(tmp_path, project_root))

    client = TestClient(api_main.app)
    response = client.post(
        "/v1/context/verify",
        json={
            "query": "Where is authentication?",
            "root": str(project_root),
            "refresh_index": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"]
    assert body["gates"], "verify route must return gate summaries"
    assert {g["name"] for g in body["gates"]} >= {"coverage", "provenance", "policy"}
    assert body["risk_level"] in {"normal", "high"}
    # The returned trace_id must resolve through the trace route.
    trace = client.get(f"/v1/traces/{body['trace_id']}")
    assert trace.status_code == 200
