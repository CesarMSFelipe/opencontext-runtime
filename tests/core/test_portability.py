"""P0 — portability: the SDD harness must run against any repo root, not just cwd.

Regression: `opencontext_run` hard-coded `HarnessRunner(root=Path.cwd())` and the
KG-indexed warning opened a bare cwd-bound `KnowledgeGraph()`, so OC's full SDD loop
could only run inside the directory the MCP server was started in — unlike a portable
prose-skill agent, which runs on any repo. These tests pin the `root`-driven behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar


def test_harness_config_surgical_defaults(tmp_path: Path) -> None:
    from opencontext_core.harness.config import HarnessConfig

    cfg = HarnessConfig()
    assert cfg.surgical_explore is True
    assert cfg.surgical_coverage_floor == 1.0
    assert cfg.auto_index_max_files == 5000

    y = tmp_path / "harness.yaml"
    y.write_text(
        "workflow_defaults:\n"
        "  surgical_explore: false\n"
        "  surgical_coverage_floor: 0.5\n"
        "  auto_index_max_files: 100\n",
        encoding="utf-8",
    )
    loaded = HarnessConfig.from_yaml_file(y)
    assert loaded.surgical_explore is False
    assert loaded.surgical_coverage_floor == 0.5
    assert loaded.auto_index_max_files == 100


class _FakeResult:
    run_id = "r1"
    status = "completed"
    artifacts: ClassVar[list] = []
    gates: ClassVar[list] = []
    warnings: ClassVar[list] = []


def test_handle_run_honors_root(tmp_path: Path, monkeypatch) -> None:
    from opencontext_core import mcp_stdio

    captured: dict = {}

    class _FakeRunner:
        def __init__(self, root, *a, **k):
            captured["root"] = Path(root)

        def run(self, workflow, task):
            return _FakeResult()

    monkeypatch.setattr("opencontext_core.harness.runner.HarnessRunner", _FakeRunner)
    server = mcp_stdio.MCPServer(db_path=str(tmp_path / "kg.db"))
    out = server._handle_run({"task": "x", "root": str(tmp_path)})

    assert captured["root"] == tmp_path.resolve()
    assert out["run_id"] == "r1"


def test_handle_run_defaults_root_to_cwd(tmp_path: Path, monkeypatch) -> None:
    from opencontext_core import mcp_stdio

    captured: dict = {}

    class _FakeRunner:
        def __init__(self, root, *a, **k):
            captured["root"] = Path(root)

        def run(self, workflow, task):
            return _FakeResult()

    monkeypatch.setattr("opencontext_core.harness.runner.HarnessRunner", _FakeRunner)
    monkeypatch.chdir(tmp_path)
    server = mcp_stdio.MCPServer(db_path=str(tmp_path / "kg.db"))
    server._handle_run({"task": "x"})

    assert captured["root"] == tmp_path.resolve()


def test_warn_kg_uses_root_db(tmp_path: Path, monkeypatch) -> None:
    from opencontext_core.harness import runner as runner_mod

    captured: dict = {}

    class _FakeKG:
        def __init__(self, db_path=None):
            captured["db_path"] = Path(db_path)

        def get_stats(self):
            return {"nodes": 0}

        def close(self):
            pass

    monkeypatch.setattr("opencontext_core.indexing.knowledge_graph.KnowledgeGraph", _FakeKG)
    r = runner_mod.HarnessRunner(root=tmp_path)

    class _State:
        def __init__(self) -> None:
            self.warnings: list = []
            self.root = tmp_path

    r._warn_if_kg_not_indexed(_State())

    assert captured["db_path"] == r.root / ".storage" / "opencontext" / "context_graph.db"


def test_sdd_runs_outside_tree(tmp_path: Path, monkeypatch) -> None:
    """Integration: a full SDD run drives the project at ``root`` even when the process
    cwd is a different, unrelated directory — and writes its artifacts under ``root``,
    never the foreign cwd. This is the portability parity a prose-skill agent has."""
    from opencontext_core.harness.runner import HarnessRunner

    project = tmp_path / "project"
    (project / "pkg").mkdir(parents=True)
    (project / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (project / "pkg" / "core.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    result = HarnessRunner(root=project).run("sdd", "add input validation to add")

    assert result.run_id
    assert "error" not in str(getattr(result, "status", "")).lower()
    # Artifacts landed under the project root, not the foreign cwd.
    assert (project / ".opencontext" / "runs").exists()
    assert not (elsewhere / ".opencontext").exists()
