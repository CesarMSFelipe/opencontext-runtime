from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from opencontext_core.config import default_config_data
from opencontext_core.runtime import OpenContextRuntime


def _create_sample_project(root: Path) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "auth.py").write_text(
        "\n".join(
            [
                "class AuthService:",
                "    def login(self, username: str) -> bool:",
                "        return bool(username)",
            ]
        ),
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# Sample\nAuthentication lives in src/auth.py\n",
        encoding="utf-8",
    )


def _runtime_factory(tmp_path: Path, project_root: Path):
    data = default_config_data()
    data["project"]["name"] = "api-test"
    data["project_index"]["root"] = str(project_root)
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    def factory() -> OpenContextRuntime:
        return OpenContextRuntime(
            config_path=config_path,
            storage_path=tmp_path / ".storage/opencontext",
        )

    return factory


def test_api_diagnostics_endpoints() -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from opencontext_api.main import app

    client = TestClient(app)
    assert client.get("/v1/security/report").status_code == 200
    assert client.post("/v1/security/scan").status_code == 200
    assert client.get("/v1/doctor").status_code == 200
    assert client.get("/v1/tokens/report").status_code == 200


def test_api_agentic_scaffold_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    import opencontext_api.main as api_main

    project_root = tmp_path / "project"
    project_root.mkdir()
    _create_sample_project(project_root)
    monkeypatch.setattr(api_main, "_runtime", _runtime_factory(tmp_path, project_root))

    client = TestClient(api_main.app)
    orchestrate = client.post(
        "/v1/orchestrate",
        json={"requirements_path": "requirements.md"},
    )
    validate = client.post("/v1/validate", json={"profile": "drupal"})
    agent_context = client.post(
        "/v1/agent-context",
        json={
            "query": "Review authentication sk-abcdefghijklmnopqrstuvwxyz123456",
            "target": "codex",
            "root": str(project_root),
            "refresh_index": True,
        },
    )

    assert orchestrate.status_code == 200
    assert orchestrate.json()["result"]["write_file"]["decision"] == "deny"
    assert validate.status_code == 200
    assert validate.json()["result"]["run_tests"]["decision"] == "ask"
    assert agent_context.status_code == 200
    assert agent_context.json()["status"] == "ready"
    assert agent_context.json()["result"]["trace_id"]
    assert "src/auth.py" in agent_context.json()["result"]["included_sources"]
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in agent_context.json()["result"]["query"]


def test_api_setup_project_without_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    response = client.post("/v1/setup", json={"root": str(project_root)})

    assert response.status_code == 200
    body = response.json()
    # Only real source files are indexed: src/auth.py + README.md. The generated
    # opencontext.yaml is excluded from the index (REQ-05), so it is not counted.
    assert body["files"] == 2
    assert (project_root / "opencontext.yaml").exists()
    assert (project_root / ".opencontext/agents/README.md").exists()
    assert (project_root / ".opencontext/models/default.yaml").exists()


def test_api_prepare_context_persists_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
        "/v1/context",
        json={
            "query": "Where is authentication?",
            "root": str(project_root),
            "refresh_index": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"]
    assert "src/auth.py" in body["included_sources"]
    trace = client.get(f"/v1/traces/{body['trace_id']}")
    assert trace.status_code == 200
    assert trace.json()["trace"]["metadata"]["context_pack"]["included"]
