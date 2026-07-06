"""Patch executor (EXE-004): a unified-diff file drives the real mutation path.

``provider: patch`` + ``patch_file: <root-relative .patch/.diff>`` in
``opencontext.yaml`` builds a :class:`PatchGateway`-backed executor that
converts the diff into schema-valid ``ApplyEdit``s and runs the FULL
production pipeline (validate → policy → checkpoint → apply → receipt →
inspection → verify). Paths must stay inside the workspace — an absolute or
escaping path is rejected and nothing is written.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.executors.patch import (
    PatchError,
    patch_to_apply_edits,
    resolve_patch_executor,
)
from opencontext_core.oc_flow import cli as oc_flow_cli
from opencontext_core.oc_flow.cli import _resolve_executor, run_oc_flow_cli
from opencontext_core.oc_flow.nodes import ProviderBackedNodeExecutor
from opencontext_core.providers.detect import DetectedProvider

_BUGGY = "def add(a, b):\n    return a - b\n"
_FIXED = "def add(a, b):\n    return a + b\n"
_TEST = "from buggy_add import add\n\n\ndef test_add() -> None:\n    assert add(2, 3) == 5\n"
_FIX_PATCH = (
    "--- a/buggy_add.py\n"
    "+++ b/buggy_add.py\n"
    "@@ -1,2 +1,2 @@\n"
    " def add(a, b):\n"
    "-    return a - b\n"
    "+    return a + b\n"
)


def _pin_mock(monkeypatch) -> None:
    monkeypatch.setattr(
        oc_flow_cli,
        "detect_provider",
        lambda: DetectedProvider(name="mock", api_key="", model="mock", source="fallback"),
    )


def _project(tmp_path: Path, *, patch_text: str = _FIX_PATCH) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "buggy_add.py").write_text(_BUGGY, encoding="utf-8")
    (root / "test_buggy_add.py").write_text(_TEST, encoding="utf-8")
    (root / "fix.patch").write_text(patch_text, encoding="utf-8")
    (root / "opencontext.yaml").write_text(
        "provider: patch\npatch_file: fix.patch\n", encoding="utf-8"
    )
    return root


# ------------------------------------------------------------- diff → ApplyEdits
def test_patch_to_apply_edits_full_file_replacement(tmp_path: Path) -> None:
    (tmp_path / "buggy_add.py").write_text(_BUGGY, encoding="utf-8")
    edits = patch_to_apply_edits(_FIX_PATCH, tmp_path)
    assert len(edits) == 1
    edit = edits[0]
    assert edit["path"] == "buggy_add.py"
    assert edit["operation"] == "replace_range"
    assert edit["start_line"] == 1
    assert edit["end_line"] == 2
    assert edit["content"] == _FIXED


def test_patch_creates_new_file(tmp_path: Path) -> None:
    patch = "--- /dev/null\n+++ b/newmod.py\n@@ -0,0 +1,2 @@\n+VALUE = 1\n+NAME = 'x'\n"
    edits = patch_to_apply_edits(patch, tmp_path)
    assert edits == [
        {
            "path": "newmod.py",
            "operation": "create_file",
            "content": "VALUE = 1\nNAME = 'x'\n",
            "reason": "apply configured patch hunk(s) to newmod.py",
            "requirement_refs": ["patch applies cleanly to newmod.py"],
        }
    ]


def test_patch_deletes_file(tmp_path: Path) -> None:
    (tmp_path / "old.py").write_text("GONE = True\n", encoding="utf-8")
    patch = "--- a/old.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-GONE = True\n"
    edits = patch_to_apply_edits(patch, tmp_path)
    assert len(edits) == 1
    assert edits[0]["path"] == "old.py"
    assert edits[0]["operation"] == "delete_file"


def test_patch_rejects_absolute_path(tmp_path: Path) -> None:
    patch = "--- a//etc/passwd\n+++ b//etc/passwd\n@@ -1 +1 @@\n-x\n+y\n"
    with pytest.raises(PatchError, match="workspace"):
        patch_to_apply_edits(patch, tmp_path)


def test_patch_rejects_parent_escape(tmp_path: Path) -> None:
    patch = "--- a/../outside.txt\n+++ b/../outside.txt\n@@ -1 +1 @@\n-x\n+y\n"
    with pytest.raises(PatchError, match="workspace"):
        patch_to_apply_edits(patch, tmp_path)


def test_patch_rejects_context_mismatch(tmp_path: Path) -> None:
    (tmp_path / "buggy_add.py").write_text("def something_else():\n    pass\n", encoding="utf-8")
    with pytest.raises(PatchError, match="does not apply"):
        patch_to_apply_edits(_FIX_PATCH, tmp_path)


def test_patch_rejects_missing_source_file(tmp_path: Path) -> None:
    with pytest.raises(PatchError, match="missing"):
        patch_to_apply_edits(_FIX_PATCH, tmp_path)


# --------------------------------------------------------------- explicit opt-in
def test_resolve_patch_executor_builds_from_explicit_config(tmp_path: Path) -> None:
    root = _project(tmp_path)
    executor = resolve_patch_executor(root)
    assert isinstance(executor, ProviderBackedNodeExecutor)
    assert executor._provider == "patch"
    assert getattr(executor, "provider_available", False) is True


def test_resolve_patch_executor_requires_config(tmp_path: Path) -> None:
    assert resolve_patch_executor(tmp_path) is None


def test_resolve_patch_executor_requires_existing_patch_file(tmp_path: Path) -> None:
    (tmp_path / "opencontext.yaml").write_text(
        "provider: patch\npatch_file: nope.patch\n", encoding="utf-8"
    )
    assert resolve_patch_executor(tmp_path) is None


def test_resolve_patch_executor_rejects_patch_file_escaping_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside.patch"
    outside.write_text(_FIX_PATCH, encoding="utf-8")
    root = tmp_path / "proj"
    root.mkdir()
    (root / "opencontext.yaml").write_text(
        "provider: patch\npatch_file: ../outside.patch\n", encoding="utf-8"
    )
    assert resolve_patch_executor(root) is None


def test_cli_resolution_builds_patch_executor(tmp_path: Path, monkeypatch) -> None:
    _pin_mock(monkeypatch)
    root = _project(tmp_path)
    executor = _resolve_executor(root)
    assert isinstance(executor, ProviderBackedNodeExecutor)
    assert executor._provider == "patch"


def test_production_config_never_builds_patch_executor(tmp_path: Path, monkeypatch) -> None:
    _pin_mock(monkeypatch)
    (tmp_path / "opencontext.yaml").write_text(
        "project:\n  name: demo\nmodels:\n  default:\n    provider: anthropic\n    model: x\n",
        encoding="utf-8",
    )
    assert _resolve_executor(tmp_path) is None


# --------------------------------------------------------- end-to-end (EXE-004)
def test_patch_run_fixes_bug_through_normal_pipeline(tmp_path: Path, monkeypatch) -> None:
    """`opencontext run` with `provider: patch` mutates + verifies for real."""
    _pin_mock(monkeypatch)
    root = _project(tmp_path)

    summary = run_oc_flow_cli(
        "Fix failing test", root=root, workflow="oc-flow", lane="fast", quiet=True
    )

    assert summary["status"] == "completed"
    assert (root / "buggy_add.py").read_text(encoding="utf-8") == _FIXED


def test_escaping_patch_blocks_run_and_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    _pin_mock(monkeypatch)
    escape = "--- a/../evil.py\n+++ b/../evil.py\n@@ -0,0 +1 @@\n+BAD = 1\n"
    root = _project(tmp_path, patch_text=escape)

    summary = run_oc_flow_cli(
        "Fix failing test", root=root, workflow="oc-flow", lane="fast", quiet=True
    )

    assert summary["status"] != "completed"
    assert not (tmp_path / "evil.py").exists()
    assert (root / "buggy_add.py").read_text(encoding="utf-8") == _BUGGY
