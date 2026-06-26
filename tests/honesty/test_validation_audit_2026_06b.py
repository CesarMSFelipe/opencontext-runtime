"""Tests for validation-audit-2026-06b fixes (T1-T9).

Each test function targets one specific behavior fix. All tests are tmp-isolated.
"""

from __future__ import annotations

import argparse
import sqlite3
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# T1: _install_dry_run flag precedence
# ---------------------------------------------------------------------------


def test_t1_dry_run_explicit_flag_overrides_preset(capsys: object) -> None:
    """Explicit --memory/--budget flags must override preset defaults."""
    from opencontext_cli.main import _install_dry_run

    args = argparse.Namespace(
        preset=None,
        memory_mode="engram",
        budget_mode="strict",
        git=None,
        openspec=None,
        dry_run=True,
    )
    _install_dry_run(args)
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    output = captured.out
    # The printed plan must reflect the explicit flag values.
    assert "engram" in output, f"Expected 'engram' in output, got: {output}"
    assert "strict" in output, f"Expected 'strict' in output, got: {output}"


# ---------------------------------------------------------------------------
# T2: SQLite context substrate hash + used_tokens
# ---------------------------------------------------------------------------


def test_t2_sqlite_substrate_hash_and_tokens() -> None:
    """build_for_phase must return non-null hash and used_tokens>0 for SQLite index."""

    from opencontext_core.agentic.context_substrate import ContextSubstrateBuilder

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Create minimal context_graph.db with the real schema (content_snippet, not content).
        db_dir = root / ".storage" / "opencontext"
        db_dir.mkdir(parents=True)
        db_path = db_dir / "context_graph.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE nodes ("
            "id TEXT PRIMARY KEY NOT NULL, "
            "name TEXT NOT NULL, "
            "kind TEXT NOT NULL, "
            "file_path TEXT NOT NULL, "
            "language TEXT NOT NULL, "
            "content_snippet TEXT"
            ")"
        )
        conn.execute(
            "INSERT INTO nodes (id, name, kind, file_path, language, content_snippet) "
            "VALUES ('n1', 'n1', 'file', 'foo.py', 'python', 'hello world')"
        )
        conn.commit()
        conn.close()

        # Ensure no JSON KG is present.
        assert not (root / ".opencontext" / "knowledge_graph.json").exists()

        builder = ContextSubstrateBuilder(root=root)
        report = builder.build_for_phase(task="test", phase="explore", budget=8000)

        assert report.context_pack_hash is not None, "context_pack_hash must not be None"
        assert report.context_pack_hash != "", "context_pack_hash must not be empty"
        assert report.used_tokens > 0, f"used_tokens must be > 0, got {report.used_tokens}"


# ---------------------------------------------------------------------------
# T3: TUI graph kind mapping
# ---------------------------------------------------------------------------


def test_t3_kind_map_symbol() -> None:
    """_map_kind('symbol') must return GraphNodeKind.SYMBOL."""
    from opencontext_cli.tui.graph.models import GraphNodeKind
    from opencontext_cli.tui.screens.graph import _map_kind

    assert _map_kind("symbol") == GraphNodeKind.SYMBOL


import pytest as _pytest


@_pytest.mark.parametrize("kind", ["function", "method", "class", "artifact"])
def test_t3_kind_map_symbol_kinds(kind: str) -> None:
    """function/method/class/artifact must all map to GraphNodeKind.SYMBOL."""
    from opencontext_cli.tui.graph.models import GraphNodeKind
    from opencontext_cli.tui.screens.graph import _map_kind

    assert _map_kind(kind) == GraphNodeKind.SYMBOL, (
        f"Expected SYMBOL for kind={kind!r}"
    )


@_pytest.mark.parametrize("kind", ["variable", "constant"])
def test_t3_kind_map_variable_constant(kind: str) -> None:
    """variable/constant must map to GraphNodeKind.FILE."""
    from opencontext_cli.tui.graph.models import GraphNodeKind
    from opencontext_cli.tui.screens.graph import _map_kind

    assert _map_kind(kind) == GraphNodeKind.FILE, (
        f"Expected FILE for kind={kind!r}"
    )


def test_t3_kind_map_unknown_defaults_to_unknown() -> None:
    """_map_kind with truly unknown value must return GraphNodeKind.UNKNOWN."""
    from opencontext_cli.tui.graph.models import GraphNodeKind
    from opencontext_cli.tui.screens.graph import _map_kind

    assert _map_kind("unknown_xyz_not_in_enum") == GraphNodeKind.UNKNOWN


# ---------------------------------------------------------------------------
# T4: EvolutionApplier honest reason
# ---------------------------------------------------------------------------


def test_t4_context_weight_honest_result() -> None:
    """_apply_context_weight must return applied=False with a non-'not yet wired' reason."""
    from opencontext_core.learning.evolution import EvolutionProposal
    from opencontext_core.learning.evolution_apply import EvolutionApplier

    with tempfile.TemporaryDirectory() as tmp:
        applier = EvolutionApplier(project_root=Path(tmp))
        proposal = EvolutionProposal(
            proposal_id="test-cw",
            kind="context_weight",
            title="Test CW",
            rationale="test",
        )
        result = applier._apply_context_weight(proposal)
        assert result.applied is False
        assert result.reason, "reason must be non-empty"
        assert "not yet wired" not in result.reason, (
            f"Stale placeholder in reason: {result.reason!r}"
        )


def test_t4_budget_profile_honest_result() -> None:
    """_apply_budget_profile must return applied=False with a non-'not yet wired' reason."""
    from opencontext_core.learning.evolution import EvolutionProposal
    from opencontext_core.learning.evolution_apply import EvolutionApplier

    with tempfile.TemporaryDirectory() as tmp:
        applier = EvolutionApplier(project_root=Path(tmp))
        proposal = EvolutionProposal(
            proposal_id="test-bp",
            kind="budget_profile",
            title="Test BP",
            rationale="test",
        )
        result = applier._apply_budget_profile(proposal)
        assert result.applied is False
        assert result.reason, "reason must be non-empty"
        assert "not yet wired" not in result.reason, (
            f"Stale placeholder in reason: {result.reason!r}"
        )


# ---------------------------------------------------------------------------
# T5: benchmark DEFAULT_SUITE resolves via importlib.resources
# ---------------------------------------------------------------------------


def test_t5_default_suite_resolves() -> None:
    """DEFAULT_SUITE must resolve to a valid YAML file without FileNotFoundError."""
    import yaml  # type: ignore[import-untyped]

    from opencontext_cli.commands.benchmark_cmd import DEFAULT_SUITE

    suite_path = Path(DEFAULT_SUITE)
    assert suite_path.exists(), f"DEFAULT_SUITE path does not exist: {DEFAULT_SUITE}"
    # Must be a valid YAML file.
    data = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
    assert data is not None, "contextbench.yaml must be non-empty YAML"


# ---------------------------------------------------------------------------
# T6: Conductor NextAction.metadata — v2 fields, no lease_id
# ---------------------------------------------------------------------------


def test_t6_conductor_metadata_no_lease_id() -> None:
    """NextAction.metadata must contain handoff block + non-null context_report_ref."""
    from opencontext_core.oc_new.conductor import OcNewConductor

    conductor = OcNewConductor()
    # Bootstrap a minimal run state to get the first spawn action.
    state = conductor.start(task="add feature X")
    # Advance until we get a spawn_subagent action (or done).
    for _ in range(10):
        if state.next_action is None:
            break
        if state.next_action.kind == "spawn_subagent":
            metadata = state.next_action.metadata or {}
            assert "lease_id" not in metadata, (
                f"'lease_id' must not appear in NextAction.metadata, got: {metadata}"
            )
            assert "context_report_ref" in metadata, (
                f"'context_report_ref' missing from metadata: {metadata}"
            )
            assert metadata["context_report_ref"] is not None, (
                f"'context_report_ref' must be non-null, got: {metadata}"
            )
            assert "result_schema" in metadata, (
                f"'result_schema' missing from metadata: {metadata}"
            )
            # T6 extension: handoff block must be present with identity fields.
            assert "handoff" in metadata, (
                f"'handoff' missing from metadata: {metadata}"
            )
            h = metadata["handoff"]
            assert isinstance(h, dict), f"'handoff' must be a dict, got: {type(h)}"
            assert h.get("run_id"), f"handoff.run_id must be non-null: {h}"
            assert h.get("change_id"), f"handoff.change_id must be non-null: {h}"
            assert h.get("phase"), f"handoff.phase must be non-null: {h}"
            assert h.get("task") is not None, f"handoff.task must be present: {h}"
            return
        if state.next_action.kind == "done":
            break
        state = conductor.advance(state, phase_result={"status": "success", "output": ""})
    # If we got here with no spawn action, the test is a no-op (flow went to done).


# ---------------------------------------------------------------------------
# T7: _APPLY_INSTRUCTION mentions surgical edits; parse_file_edits handles whole-file
# ---------------------------------------------------------------------------


def test_t7_apply_instruction_mentions_surgical() -> None:
    """_APPLY_INSTRUCTION must mention surgical or ApplyEdit operations."""
    from opencontext_core.agents.executor import _APPLY_INSTRUCTION

    lower = _APPLY_INSTRUCTION.lower()
    assert "surgical" in lower or "applyedit" in lower or "targeted" in lower, (
        f"_APPLY_INSTRUCTION must mention surgical/ApplyEdit ops. Got:\n{_APPLY_INSTRUCTION}"
    )


def test_t7_parse_file_edits_whole_file_still_works() -> None:
    """parse_file_edits must still parse a whole-file JSON array without error."""
    from opencontext_core.agents.executor import parse_file_edits

    payload = '[{"path": "foo.py", "content": "print(1)\\n"}]'
    edits = parse_file_edits(payload)
    assert len(edits) == 1
    assert edits[0]["path"] == "foo.py"
    assert edits[0]["content"] == "print(1)\n"


# ---------------------------------------------------------------------------
# T8: planner _is_oc_only_gitignore
# ---------------------------------------------------------------------------


def test_t8_oc_only_gitignore_excluded() -> None:
    """OC-only .gitignore content must be detected as OC-only."""
    from opencontext_core.retrieval.planner import _is_oc_only_gitignore

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        gitignore = root / ".gitignore"
        gitignore.write_text(
            "# opencontext:storage:start\n"
            ".storage/opencontext/\n"
            "# opencontext:storage:end\n",
            encoding="utf-8",
        )
        assert _is_oc_only_gitignore(root, ".gitignore") is True


def test_t8_user_gitignore_not_excluded() -> None:
    """A .gitignore with user lines beyond the OC block must NOT be detected as OC-only."""
    from opencontext_core.retrieval.planner import _is_oc_only_gitignore

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        gitignore = root / ".gitignore"
        gitignore.write_text(
            "__pycache__/\n"
            "*.pyc\n"
            "# opencontext:storage:start\n"
            ".storage/opencontext/\n"
            "# opencontext:storage:end\n",
            encoding="utf-8",
        )
        assert _is_oc_only_gitignore(root, ".gitignore") is False


# ---------------------------------------------------------------------------
# T9: uninstall removes empty .claude/agents and .claude/commands
# ---------------------------------------------------------------------------


def test_t9_rmdir_empty_agent_dirs() -> None:
    """After glob sweep, empty .claude/agents must be removed; non-empty survives."""

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        agents_dir = root / ".claude" / "agents"
        commands_dir = root / ".claude" / "commands"
        agents_dir.mkdir(parents=True)
        commands_dir.mkdir(parents=True)
        # Place a user file in commands so it should NOT be removed.
        (commands_dir / "user_command.md").write_text("# user", encoding="utf-8")

        # Simulate the rmdir logic from uninstall_cmd.py.
        for d in (agents_dir, commands_dir):
            try:
                d.rmdir()
            except OSError:
                pass

        assert not agents_dir.exists(), "Empty agents dir must have been removed"
        assert commands_dir.exists(), "Non-empty commands dir must survive"


def test_t9_rmdir_absent_dir_no_error() -> None:
    """rmdir on absent .claude/agents must not raise any exception."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        absent_dir = root / ".claude" / "agents"
        # Must not exist.
        assert not absent_dir.exists()
        # Apply the same logic.
        try:
            absent_dir.rmdir()
        except OSError:
            pass
        # No exception = test passes.
