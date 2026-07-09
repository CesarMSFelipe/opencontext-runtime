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
    # Headline baseline is reading the RELEVANT FILES WHOLE, not the whole project.
    assert "read the relevant files whole" in out
    assert "reads the whole project" not in out
    # The whole-repo total is only a clearly-labeled secondary ceiling line.
    assert "Whole-repo ceiling" in out
    # Honest headline: a real reduction ("% less") on large repos, or a truthful
    # "no reduction at this size" on a tiny one — never a false "0.0% less".
    assert ("less" in out) or ("no reduction" in out)
    assert "0.0% less" not in out


def test_demo_headline_baseline_is_pack_files_not_whole_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    # A repo with one relevant code file and a big unrelated doc. The headline baseline
    # must be the pack's own files (small), NOT the whole repo (dominated by the big
    # doc the pack never draws from) — the whole-repo number appears only on the ceiling
    # line. A large .md is counted by the whole-repo ceiling but is not pulled into the
    # pack for a code query, so the two baselines are guaranteed to differ.
    project_root = tmp_path / "project"
    (project_root / "src").mkdir(parents=True)
    (project_root / "src" / "auth.py").write_text(
        "def login(user):\n    return bool(user)\n", encoding="utf-8"
    )
    (project_root / "docs.md").write_text("# Guide\n" + ("word " * 8000), encoding="utf-8")

    runtime = OpenContextRuntime(
        config_path=_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/opencontext",
    )
    args = SimpleNamespace(path=str(project_root), query="where is login")

    assert handle_demo(runtime, args) == 0
    out = capsys.readouterr().out

    from opencontext_core.evaluation.telemetry import (
        estimate_included_files_tokens,
        estimate_naive_tokens,
    )

    pack = runtime.build_context_pack("where is login")
    honest = estimate_included_files_tokens(project_root, pack)
    whole_repo = estimate_naive_tokens(project_root)

    # The two baselines must actually differ here (the big unrelated file guarantees it),
    # proving the headline is NOT the whole-repo number.
    assert whole_repo > honest
    # The honest baseline prints as the headline "Without OpenContext" figure.
    assert f"{honest:,} tokens" in out
    # The whole-repo total prints only on the labeled ceiling line.
    assert f"Whole-repo ceiling (if an agent read everything): {whole_repo:,} tokens" in out


def test_demo_rejects_missing_path(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    runtime = OpenContextRuntime(
        config_path=_config(tmp_path, tmp_path),
        storage_path=tmp_path / ".storage/opencontext",
    )
    args = SimpleNamespace(path=str(tmp_path / "nope"), query="x")
    assert handle_demo(runtime, args) == 1
    # Errors are routed to stderr (brand eprint) so --json/stdout stays clean.
    assert "Not a directory" in capsys.readouterr().err
