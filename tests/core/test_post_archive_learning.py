"""Tests for post-archive learning hook (CAP6 — approval-gated lesson capture).

The conductor exposes ``propose_archive_lessons`` which writes a lesson
proposal to a namespaced project path ONLY when ``approved=True``. It MUST
NOT touch ``~/.claude/skills/`` and MUST be a no-op when AUTOMATIC flow
runs without an explicit approval flag.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from opencontext_core.agentic.config import AgenticFlowConfig, FlowMode
from opencontext_core.oc_new.conductor import OcNewConductor


def _home_fake(tmp_path: Path) -> Path:
    """Point Path.home() at a sandbox dir so any leak to ~/.claude/skills is detectable."""
    fake = tmp_path / "fake_home"
    fake.mkdir()
    return fake


def test_post_archive_noop_when_automatic_without_approval(tmp_path: Path) -> None:
    fake_home = _home_fake(tmp_path)
    conductor = OcNewConductor(root=tmp_path)
    cfg = AgenticFlowConfig(flow_mode=FlowMode.AUTOMATIC)

    with patch.object(Path, "home", lambda: fake_home):
        result = conductor.propose_archive_lessons(
            run_id="run-1",
            change_id="my-change",
            approved=False,
            config=cfg,
        )

    assert result is None
    assert not (fake_home / ".claude" / "skills").exists()


def test_post_archive_noop_when_stepwise_without_approval(tmp_path: Path) -> None:
    """STEPWISE without explicit approval also writes nothing."""
    fake_home = _home_fake(tmp_path)
    conductor = OcNewConductor(root=tmp_path)
    cfg = AgenticFlowConfig(flow_mode=FlowMode.STEPWISE)

    with patch.object(Path, "home", lambda: fake_home):
        result = conductor.propose_archive_lessons(
            run_id="run-2",
            change_id="another-change",
            approved=False,
            config=cfg,
            lessons=["something learned"],
        )

    assert result is None
    assert not (fake_home / ".claude" / "skills").exists()


def test_post_archive_writes_namespaced_proposal_when_approved(tmp_path: Path) -> None:
    fake_home = _home_fake(tmp_path)
    conductor = OcNewConductor(root=tmp_path)
    cfg = AgenticFlowConfig(flow_mode=FlowMode.STEPWISE)

    with patch.object(Path, "home", lambda: fake_home):
        path = conductor.propose_archive_lessons(
            run_id="run-3",
            change_id="approved-change",
            approved=True,
            config=cfg,
            lessons=["Lesson one", "Lesson two"],
        )

    assert path is not None
    # ponytail: project namespace, NEVER ~/.claude/skills/.
    assert "~/.claude/skills" not in str(path)
    assert str(path).endswith(".json")
    assert str(path).startswith(str(tmp_path))
    payload = json.loads(path.read_text())
    assert payload["run_id"] == "run-3"
    assert payload["change_id"] == "approved-change"
    assert payload["lessons"] == ["Lesson one", "Lesson two"]


def test_post_archive_never_writes_to_claude_skills(tmp_path: Path, monkeypatch) -> None:
    """Defence-in-depth: scan the whole fake home for any skill file leak."""
    fake_home = _home_fake(tmp_path)
    conductor = OcNewConductor(root=tmp_path)
    cfg = AgenticFlowConfig(flow_mode=FlowMode.HYBRID)

    with patch.object(Path, "home", lambda: fake_home):
        conductor.propose_archive_lessons(
            run_id="run-4",
            change_id="safe-change",
            approved=True,
            config=cfg,
            lessons=["ok"],
        )
        conductor.propose_archive_lessons(
            run_id="run-5",
            change_id="safe-change-2",
            approved=False,
            config=cfg,
            lessons=["ignored"],
        )

    # ponytail: walk all files under fake_home and assert none is under ~/.claude/skills.
    for f in fake_home.rglob("*"):
        if f.is_file():
            assert ".claude" not in f.parts, f"unexpected leak to {f}"


@pytest.fixture(autouse=True)
def _legacy_local_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """This module asserts the legacy in-repo layout; pin local storage mode."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
