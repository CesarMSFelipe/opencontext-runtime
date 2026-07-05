"""TDD — C10: real unified diff in patch.diff via difflib (OQ-1 resolved).

OQ-1 resolution: CheckpointStore.create captures pre-edit bytes in
checkpoint.dir / "files" / snap.blob for each file. No additional snapshot
assignment is needed in node_mutate — the checkpoint's existing files list
provides the before bytes.

RED gate: node_mutate currently writes a comment-string, not a real unified
diff. The tests assert ---/+++/@@ markers and git-apply-ability.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from opencontext_core.agents.executor import ApplyEdit, ApplyOperation
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.nodes import (
    DeterministicNodeExecutor,
    OCFlowContext,
    node_gather_context,
    node_mutate,
    node_plan,
)


def _ctx(root: Path, edits: list[ApplyEdit]) -> OCFlowContext:
    artifacts = root / "artifacts" / "oc-flow"
    artifacts.mkdir(parents=True, exist_ok=True)
    return OCFlowContext(
        root=root,
        artifacts_dir=artifacts,
        task="Replace content in source file",
        lane=Lane.FAST,
        profile="balanced",
        executor=DeterministicNodeExecutor(requested_edits=edits),
        max_attempts=2,
        seed_paths=[],
    )


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with one committed source file."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    # Force LF-only line endings so the patch (written as raw bytes) applies
    # cleanly on Windows where autocrlf would otherwise inject CRLF.
    subprocess.run(
        ["git", "config", "core.autocrlf", "false"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    src = tmp_path / "src.py"
    # Write raw LF bytes — Path.write_text would translate to CRLF on
    # Windows in text mode and create a mismatch with the patch.
    src.write_bytes(b"# original\nVALUE = 1\nEND = True\n")
    subprocess.run(["git", "add", "src.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


def test_patch_diff_is_git_applicable(git_repo: Path) -> None:
    """patch.diff produced by node_mutate must be applicable via git apply --check."""
    edit = ApplyEdit(
        path="src.py",
        operation=ApplyOperation.REPLACE_RANGE,
        start_line=2,
        end_line=2,
        content="VALUE = 42\n",
        reason="update value",
        requirement_refs=["task addressed"],
    )
    ctx = _ctx(git_repo, edits=[edit])
    node_gather_context(ctx)
    node_plan(ctx)
    node_mutate(ctx)

    patch_path = ctx.artifacts_dir / "patch.diff"
    assert patch_path.exists(), "patch.diff must exist after node_mutate"

    patch_content = patch_path.read_text(encoding="utf-8")

    # Assert unified diff markers
    assert "---" in patch_content, "patch.diff must contain --- header"
    assert "+++" in patch_content, "patch.diff must contain +++ header"
    assert "@@" in patch_content, "patch.diff must contain @@ hunk marker"

    # Restore the file to pre-edit state for git apply check
    subprocess.run(
        ["git", "checkout", "HEAD", "--", "src.py"],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )

    # git apply --check validates the patch without modifying the working tree
    result = subprocess.run(
        ["git", "apply", "--check", str(patch_path)],
        cwd=git_repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"git apply --check failed (exit {result.returncode}):\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}\n"
        f"patch:\n{patch_content}"
    )


def test_patch_diff_contains_unified_diff_markers(git_repo: Path) -> None:
    """patch.diff contains ---/+++/@@ on any mutating run."""
    edit = ApplyEdit(
        path="src.py",
        operation=ApplyOperation.REPLACE_RANGE,
        start_line=3,
        end_line=3,
        content="END = False\n",
        reason="flip flag",
        requirement_refs=["test criterion"],
    )
    ctx = _ctx(git_repo, edits=[edit])
    node_gather_context(ctx)
    node_plan(ctx)
    node_mutate(ctx)

    content = (ctx.artifacts_dir / "patch.diff").read_text(encoding="utf-8")
    assert "---" in content
    assert "+++" in content
    assert "@@" in content
