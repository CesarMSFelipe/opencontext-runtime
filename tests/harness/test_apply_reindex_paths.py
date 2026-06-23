"""ApplyPhase must hand `reindex_files` ROOT-RELATIVE paths. The KG keys every node by
relative path; an absolute path writes duplicate absolute-keyed nodes and never prunes
the stale pre-change relative-keyed ones, so verify/review would keep reading the old
graph. Regression for the adversarial-review finding."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.models import BudgetMode
from opencontext_core.harness.runner import HarnessRunner


def test_apply_reindexes_with_relative_paths(tmp_path: Path, monkeypatch) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "core.py").write_text("def old():\n    return 1\n", encoding="utf-8")

    runner = HarnessRunner(root=tmp_path)
    state = runner.create_run("sdd", "edit core")
    # Relative edit path → the executor records an ABSOLUTE change path; the fix must
    # convert it back to root-relative before reindexing.
    state.apply_edits = [{"path": "pkg/core.py", "content": "def old():\n    return 2\n"}]

    captured: dict = {}
    from opencontext_core.runtime import OpenContextRuntime

    def _fake_reindex(self, changed_paths, root=None):
        captured["paths"] = set(changed_paths)
        return {}

    monkeypatch.setattr(OpenContextRuntime, "reindex_files", _fake_reindex)

    runner._build_phase("apply", BudgetMode.OFF).run(state)

    assert captured.get("paths"), "reindex was not called with the changed file"
    for p in captured["paths"]:
        assert not p.startswith("/"), f"absolute path leaked to reindex: {p}"
    assert "pkg/core.py" in captured["paths"]
