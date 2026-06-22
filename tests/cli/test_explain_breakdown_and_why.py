"""`opencontext explain --breakdown` / `--why FILE` — per-signal observability.

These surface data already on ``pack.included`` items; no retrieval-pipeline
change is permitted (B3-REQ-1, B3-REQ-2; Scenarios B3-1a, B3-2a, B3-2b).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from opencontext_cli.commands.explain_cmd import _breakdown, handle_explain
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


def _runtime(tmp_path: Path) -> tuple[OpenContextRuntime, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/opencontext",
    )
    runtime.index_project(project_root)
    return runtime, project_root


# ── _breakdown unit (per-signal components from item fields + metadata) ───────


def test_breakdown_renders_per_signal_components() -> None:
    item = SimpleNamespace(
        priority=SimpleNamespace(value="p1"),
        source_trust=0.8,
        metadata={
            "retrieval_source": "graph",
            "freshness": "unknown",
            "retrieval": {"kind": "function", "node": "login"},
        },
    )
    line = _breakdown(item)
    # The signal components present on the item are surfaced (not just source/score).
    assert "trust" in line
    assert "0.80" in line
    assert "p1" in line
    assert "freshness" in line or "unknown" in line


def test_breakdown_falls_back_cleanly_with_no_signals() -> None:
    item = SimpleNamespace(priority=SimpleNamespace(value="p2"), source_trust=0.5, metadata={})
    # Must not raise and must still report the always-present fields.
    line = _breakdown(item)
    assert "trust" in line
    assert "p2" in line


# ── --breakdown end-to-end (adds a signals column to the table) ───────────────


def test_explain_breakdown_adds_signal_columns(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    runtime, project_root = _runtime(tmp_path)
    args = SimpleNamespace(
        query="Where is authentication implemented?",
        root=str(project_root),
        max_tokens=1200,
        breakdown=True,
        why=None,
    )
    assert handle_explain(runtime, args) == 0
    out = capsys.readouterr().out
    assert "Why this context" in out
    # The breakdown surfaces a per-signal column beyond source/score/tok.
    assert "signals" in out.lower() or "trust" in out.lower()


# ── --why FILE end-to-end (single-file rationale + absent message) ────────────


def test_explain_why_prints_rationale_for_included_file(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    runtime, project_root = _runtime(tmp_path)
    # Build the pack once to discover an actually-included source path.
    pack = runtime.build_context_pack("Where is authentication implemented?", 1200)
    assert pack.included, "fixture should include at least one item"
    target = pack.included[0].source

    args = SimpleNamespace(
        query="Where is authentication implemented?",
        root=str(project_root),
        max_tokens=1200,
        breakdown=False,
        why=target,
    )
    assert handle_explain(runtime, args) == 0
    out = capsys.readouterr().out
    assert target in out
    # rationale (the _why scaffold output / score / tokens) is shown for that file
    assert "score" in out.lower() or "tok" in out.lower() or "why" in out.lower()


def test_explain_why_absent_file_prints_not_included(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    runtime, project_root = _runtime(tmp_path)
    args = SimpleNamespace(
        query="Where is authentication implemented?",
        root=str(project_root),
        max_tokens=1200,
        breakdown=False,
        why="does/not/exist_xyz.py",
    )
    # Must be non-crashing (exit 0) and print a clear "not included" message.
    assert handle_explain(runtime, args) == 0
    out = capsys.readouterr().out
    assert "not included" in out.lower()
