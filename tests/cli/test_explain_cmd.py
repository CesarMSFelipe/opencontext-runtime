"""`opencontext explain` — the why-this-context audit view."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from opencontext_cli.commands.explain_cmd import _why, handle_explain
from opencontext_core.config import default_config_data
from opencontext_core.runtime import OpenContextRuntime


def write_config(tmp_path: Path, project_root: Path) -> Path:
    data = default_config_data()
    data["project"]["name"] = "test-project"
    data["project_index"]["root"] = str(project_root)
    data["retrieval"]["top_k"] = 10
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return config_path


def create_sample_project(root: Path) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "auth.py").write_text(
        "class AuthService:\n    def login(self, username: str) -> bool:\n"
        "        return bool(username)\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# Sample\nAuthentication lives in src/auth.py\n", encoding="utf-8"
    )


def test_why_describes_graph_signal() -> None:
    item = SimpleNamespace(
        metadata={
            "retrieval_source": "graph",
            "retrieval": {"node": "login", "kind": "function", "relationships": ["search_match"]},
        },
        redacted=False,
    )
    why = _why(item)
    assert "graph" in why
    assert "function login" in why
    assert "matched query" in why


def test_why_flags_redaction() -> None:
    item = SimpleNamespace(metadata={"retrieval_source": "manifest"}, redacted=True)
    assert "secret redacted" in _why(item)


def test_why_falls_back_when_no_signal() -> None:
    assert _why(SimpleNamespace(metadata={}, redacted=False)) == "ranked candidate"


def test_handle_explain_renders_for_a_task(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/opencontext",
    )
    runtime.index_project(project_root)
    args = SimpleNamespace(
        query="Where is authentication implemented?", root=str(project_root), max_tokens=1200
    )

    assert handle_explain(runtime, args) == 0
    out = capsys.readouterr().out
    assert "Why This Context" in out
    assert "auth" in out  # the relevant file surfaces in the explanation
