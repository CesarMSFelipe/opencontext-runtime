"""`opencontext demo` — the before/after aha on the user's own repo."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from opencontext_cli.commands.demo_cmd import handle_demo
from opencontext_core.config import default_config_data
from opencontext_core.runtime import OpenContextRuntime


def _config(tmp_path: Path, project_root: Path) -> Path:
    data = default_config_data()
    data["project"]["name"] = "demo-project"
    data["project_index"]["root"] = str(project_root)
    path = tmp_path / "opencontext.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_demo_shows_before_after(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    project_root = tmp_path / "project"
    (project_root / "src").mkdir(parents=True)
    (project_root / "src" / "auth.py").write_text(
        "def login(user):\n    return bool(user)\n", encoding="utf-8"
    )
    (project_root / "README.md").write_text("Auth in src/auth.py\n", encoding="utf-8")

    runtime = OpenContextRuntime(
        config_path=_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/opencontext",
    )
    args = SimpleNamespace(path=str(project_root), query="where is login")

    assert handle_demo(runtime, args) == 0
    out = capsys.readouterr().out
    assert "OpenContext Demo" in out
    assert "Without OpenContext" in out
    # Honest headline: a real reduction ("% less") on large repos, or a truthful
    # "no reduction at this size" on a tiny one — never a false "0.0% less".
    assert ("less" in out) or ("no reduction" in out)
    assert "0.0% less" not in out


def test_demo_rejects_missing_path(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    runtime = OpenContextRuntime(
        config_path=_config(tmp_path, tmp_path),
        storage_path=tmp_path / ".storage/opencontext",
    )
    args = SimpleNamespace(path=str(tmp_path / "nope"), query="x")
    assert handle_demo(runtime, args) == 1
    # Errors are routed to stderr (brand eprint) so --json/stdout stays clean.
    assert "Not a directory" in capsys.readouterr().err
