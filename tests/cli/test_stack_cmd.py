"""`opencontext stack` — detection, rendering, and AGENTS.md injection."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from opencontext_cli.commands.stack_cmd import _select_stacks, handle_stack
from opencontext_profiles.standards import (
    KNOWN_PROFILES,
    render_stack_standards,
    standards_for,
)


def test_render_includes_all_reviewer_buckets() -> None:
    md = render_stack_standards(["python"])
    assert "### Python" in md
    assert "**Format:**" in md and "ruff format" in md
    assert "**Static review:**" in md and "mypy" in md
    assert "**Dynamic review:**" in md
    assert "**Testing:**" in md
    assert "**Standards:**" in md


def test_unknown_stack_falls_back_to_generic() -> None:
    assert standards_for("cobol").profile == "generic"
    md = render_stack_standards([])  # nothing detected
    assert "### General" in md


def test_select_drops_low_confidence_and_tooling() -> None:
    # python is curated + confident; make is tooling (no curated standards);
    # rust here is a single stray fixture marker (below threshold).
    scored = [(1.0, "python"), (0.67, "make"), (0.33, "rust")]
    chosen, dropped = _select_stacks(scored, KNOWN_PROFILES)
    assert chosen == ["python"]
    assert "make" in dropped and "rust" in dropped


def test_select_keeps_strongest_when_none_clear_threshold() -> None:
    # A small real project: one curated stack, just under the bar — still shown.
    chosen, _ = _select_stacks([(0.33, "go")], KNOWN_PROFILES)
    assert chosen == ["go"]


def test_write_injects_idempotent_managed_block(tmp_path: Path) -> None:
    # A Python project marker so detection is deterministic.
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# Notes\n\nKeep me.\n", encoding="utf-8")

    args = SimpleNamespace(path=str(tmp_path), write=True)
    assert handle_stack(args) == 0

    body = agents.read_text(encoding="utf-8")
    assert "Keep me." in body  # user content preserved
    assert "<!-- opencontext:stack:start -->" in body
    assert "### Python" in body

    # Idempotent: second run leaves the file byte-identical.
    assert handle_stack(args) == 0
    assert agents.read_text(encoding="utf-8") == body
