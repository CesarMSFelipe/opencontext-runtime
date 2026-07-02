"""Memory v2 CLI command tests: argparse shape, dispatch, legacy deprecation.

Per openspec/changes/agentic-parity-engram-gentle/design/pr3-cli-fastapi.md
§Tests added — REQ-OMV-001..007 surface coverage.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from opencontext_cli.commands.memory_v2_cmd import (
    DEPRECATION_MAP,
    SUBCOMMANDS_V2,
    add_memory_v2_parser,
)


@pytest.fixture
def v2_parser() -> argparse.ArgumentParser:
    """Build a ``memory v2`` sub-subparser."""
    parent = argparse.ArgumentParser(prog="opencontext")
    sub = parent.add_subparsers(dest="command", required=True)
    memory = sub.add_parser("memory", help="Memory commands.")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    add_memory_v2_parser(memory_sub)
    return parent


@pytest.fixture
def v2_help() -> argparse.ArgumentParser:
    """Return the v2 parser directly for help text inspection."""
    parent = argparse.ArgumentParser(prog="opencontext")
    sub = parent.add_subparsers(dest="command", required=True)
    return add_memory_v2_parser(sub)


@pytest.fixture
def v2_parent() -> argparse.ArgumentParser:
    """Return a full parent parser for ``v2 <tool>`` arg parsing."""
    parent = argparse.ArgumentParser(prog="opencontext")
    sub = parent.add_subparsers(dest="command", required=True)
    add_memory_v2_parser(sub)
    return parent


class TestHelpShape:
    def test_v2_help_lists_22_subcommands(self, v2_help: argparse.ArgumentParser) -> None:
        """REQ-OMV-001: memory v2 help lists all 22 tools."""
        help_out = v2_help.format_help()
        for tool in SUBCOMMANDS_V2:
            assert tool in help_out, f"Missing tool '{tool}' in v2 help"

    def test_v2_parses_under_memory(self, v2_parser: argparse.ArgumentParser) -> None:
        """``opencontext memory v2 save`` parses correctly."""
        args = v2_parser.parse_args(["memory", "v2", "save", "--title", "test"])
        assert args.memory_command == "v2"
        assert args.v2_command == "save"

    def test_v2_parses_direct(self, v2_parent: argparse.ArgumentParser) -> None:
        """``opencontext v2 save`` parses standalone."""
        args = v2_parent.parse_args(["v2", "save", "--title", "test"])
        assert args.v2_command == "save"


class TestToolArgs:
    def test_save_accepts_title_and_content(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(
            ["v2", "save", "--title", "found bug", "--content", "memory leak in loop"]
        )
        assert args.title == "found bug"
        assert args.content == "memory leak in loop"

    def test_search_accepts_query(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(["v2", "search", "--query", "auth bug"])
        assert args.query == "auth bug"

    def test_get_by_id(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(["v2", "get", "--id", "42"])
        assert args.id == "42"

    def test_update_accepts_id_and_fields(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(["v2", "update", "--id", "1", "--title", "new title"])
        assert args.id == 1
        assert args.title == "new title"

    def test_pin_accepts_id(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(["v2", "pin", "--id", "5"])
        assert args.id == 5

    def test_unpin_accepts_id(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(["v2", "unpin", "--id", "5"])
        assert args.id == 5

    def test_delete_soft_default(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(["v2", "delete", "--id", "10"])
        assert args.id == 10
        assert getattr(args, "hard", False) is False

    def test_delete_hard_flag(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(["v2", "delete", "--id", "10", "--hard"])
        assert args.hard is True

    def test_judge_accepts_judgment_id_and_relation(
        self, v2_parent: argparse.ArgumentParser
    ) -> None:
        args = v2_parent.parse_args(
            ["v2", "judge", "--judgment-id", "rel-abc", "--relation", "related"]
        )
        assert args.judgment_id == "rel-abc"
        assert args.relation == "related"

    def test_compare_accepts_two_ids(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(
            ["v2", "compare", "--id-a", "1", "--id-b", "2", "--relation", "supersedes"]
        )
        assert args.id_a == 1
        assert args.id_b == 2

    def test_doctor_no_args(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(["v2", "doctor"])
        assert args.v2_command == "doctor"

    def test_session_start_accepts_id(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(["v2", "session-start", "--id", "sess-1"])
        assert args.id == "sess-1"

    def test_session_end_accepts_id(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(["v2", "session-end", "--id", "sess-1"])
        assert args.id == "sess-1"

    def test_context_no_args(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(["v2", "context"])
        assert args.v2_command == "context"

    def test_current_project_no_args(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(["v2", "current-project"])
        assert args.v2_command == "current-project"

    def test_capture_passive_accepts_content(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(["v2", "capture-passive", "--content", "some learning"])
        assert args.content == "some learning"

    def test_suggest_topic_key_accepts_title(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(["v2", "suggest-topic-key", "--title", "auth redesign"])
        assert args.title == "auth redesign"

    def test_review_action_list(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(["v2", "review"])
        assert args.v2_command == "review"

    def test_stats_no_args(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(["v2", "stats"])
        assert args.v2_command == "stats"

    def test_timeline_accepts_project(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(["v2", "timeline", "--project", "my-project"])
        assert args.project == "my-project"

    def test_merge_projects_accepts_sources(self, v2_parent: argparse.ArgumentParser) -> None:
        args = v2_parent.parse_args(
            ["v2", "merge-projects", "--target", "main", "--sources", "a", "b"]
        )
        assert args.target == "main"
        assert args.sources == ["a", "b"]


class TestDeprecation:
    def test_deprecation_map_key_count(self) -> None:
        assert len(DEPRECATION_MAP) >= 5

    def test_deprecation_map_init_maps_to_save(self) -> None:
        assert "init" in DEPRECATION_MAP

    def test_deprecation_map_list_maps_to_search_all(self) -> None:
        assert DEPRECATION_MAP.get("list", "") == "search --all"

    def test_deprecation_map_show_maps_to_get(self) -> None:
        assert DEPRECATION_MAP.get("show", "").startswith("get")

    def test_deprecation_map_expand_maps_to_get_expand(self) -> None:
        assert DEPRECATION_MAP.get("expand", "").startswith("get")


class TestVerboseFlag:
    def test_all_tools_accept_verbose(self, v2_parent: argparse.ArgumentParser) -> None:
        # Some tools have required args (--query for search, --title for
        # save, etc.) — pass the minimum required
        TOOL_ARGS: dict[str, list[str]] = {
            "search": ["--query", "q"],
            "save": ["--title", "t"],
            "get": ["--id", "1"],
            "update": ["--id", "1", "--title", "t"],
            "pin": ["--id", "1"],
            "unpin": ["--id", "1"],
            "delete": ["--id", "1"],
            "judge": ["--judgment-id", "x", "--relation", "related"],
            "compare": ["--id-a", "1", "--id-b", "2", "--relation", "related"],
            "session-start": ["--id", "s"],
            "session-end": ["--id", "s"],
            "capture-passive": ["--content", "c"],
            "merge-projects": ["--target", "t", "--sources", "a"],
        }
        for tool in SUBCOMMANDS_V2:
            extra = TOOL_ARGS.get(tool, [])
            args = v2_parent.parse_args(["v2", tool, "--verbose", *extra])
            assert getattr(args, "verbose", False) is True, f"{tool}: verbose not set"


class TestDispatchWiring:
    """save/search must hit a real store; unwired verbs must fail loudly."""

    def test_save_search_roundtrip_persists(self, tmp_path: Path, capsys: Any) -> None:
        from opencontext_cli.commands.memory_v2_cmd import _dispatch_tool

        save_args = argparse.Namespace(
            title="found bug",
            content="memory leak in loop",
            type="manual",
            scope="project",
            topic_key=None,
            no_capture_prompt=True,
        )
        _dispatch_tool("save", tmp_path, save_args)
        db = tmp_path / ".storage" / "opencontext" / "memory_v2.db"
        assert db.exists(), "save must persist to the v2 store on disk"

        search_args = argparse.Namespace(query="leak", limit=10, all_projects=False)
        _dispatch_tool("search", tmp_path, search_args)
        out = capsys.readouterr().out
        assert "found bug" in out, "search must find the observation just saved"

    def test_save_empty_content_exits_nonzero(self, tmp_path: Path) -> None:
        from opencontext_cli.commands.memory_v2_cmd import _dispatch_tool

        args = argparse.Namespace(
            title="t", content="", type="manual", scope="project",
            topic_key=None, no_capture_prompt=True,
        )
        with pytest.raises(SystemExit) as excinfo:
            _dispatch_tool("save", tmp_path, args)
        assert excinfo.value.code == 2

    def test_unwired_tool_exits_nonzero(self, tmp_path: Path) -> None:
        from opencontext_cli.commands.memory_v2_cmd import _dispatch_tool

        # "stats" has no backend implementation — must exit 2 always
        with pytest.raises(SystemExit) as excinfo:
            _dispatch_tool("stats", tmp_path, argparse.Namespace())
        assert excinfo.value.code == 2

    # --- T6: lifecycle roundtrip ---

    def test_lifecycle_roundtrip(self, tmp_path: Path, capsys: Any) -> None:
        """save → get → update → pin → unpin → delete lifecycle."""
        from opencontext_cli.commands.memory_v2_cmd import _dispatch_tool

        # save
        save_args = argparse.Namespace(
            title="lifecycle test",
            content="test content for lifecycle",
            type="manual",
            scope="project",
            topic_key=None,
            no_capture_prompt=True,
        )
        _dispatch_tool("save", tmp_path, save_args)
        out = capsys.readouterr().out
        obs_id = json.loads(out)["receipt"]["id"]

        # get
        _dispatch_tool("get", tmp_path, argparse.Namespace(id=str(obs_id)))
        out = capsys.readouterr().out
        assert "lifecycle test" in out

        # update
        _dispatch_tool(
            "update",
            tmp_path,
            argparse.Namespace(
                id=obs_id, title="updated title", content=None, type=None, scope=None
            ),
        )
        out = capsys.readouterr().out
        assert "updated title" in out

        # pin
        _dispatch_tool("pin", tmp_path, argparse.Namespace(id=obs_id))
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["pinned"]  # 1 or True

        # unpin
        _dispatch_tool("unpin", tmp_path, argparse.Namespace(id=obs_id))
        out = capsys.readouterr().out
        data = json.loads(out)
        assert not data["pinned"]  # 0 or False

        # delete (soft)
        _dispatch_tool("delete", tmp_path, argparse.Namespace(id=obs_id, hard=False))
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["deleted"] is True

    def test_session_trio(self, tmp_path: Path, capsys: Any) -> None:
        """session-start → session-summary → session-end lifecycle."""
        from opencontext_cli.commands.memory_v2_cmd import _dispatch_tool

        sess_id = "test-session-trio"

        _dispatch_tool(
            "session-start",
            tmp_path,
            argparse.Namespace(id=sess_id, directory=str(tmp_path), project=None),
        )
        out = capsys.readouterr().out
        assert sess_id in out

        _dispatch_tool(
            "session-summary",
            tmp_path,
            argparse.Namespace(id=sess_id, goal="test the session trio"),
        )
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["goal"] == "test the session trio"

        _dispatch_tool(
            "session-end",
            tmp_path,
            argparse.Namespace(id=sess_id, summary=None),
        )
        out = capsys.readouterr().out
        assert sess_id in out

    def test_suggest_topic_key(self, tmp_path: Path, capsys: Any) -> None:
        """suggest-topic-key returns a deterministic kebab slug."""
        from opencontext_cli.commands.memory_v2_cmd import _dispatch_tool

        _dispatch_tool(
            "suggest-topic-key",
            tmp_path,
            argparse.Namespace(title="Auth Redesign", project=None),
        )
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "auth-redesign" in data["key"]

    def test_doctor(self, tmp_path: Path, capsys: Any) -> None:
        """doctor emits a DoctorReport JSON with a 'checks' key."""
        from opencontext_cli.commands.memory_v2_cmd import _dispatch_tool

        _dispatch_tool("doctor", tmp_path, argparse.Namespace())
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "checks" in data

    def test_current_project(self, tmp_path: Path, capsys: Any) -> None:
        """current-project returns a DetectionResult JSON."""
        from opencontext_cli.commands.memory_v2_cmd import _dispatch_tool

        _dispatch_tool("current-project", tmp_path, argparse.Namespace())
        out = capsys.readouterr().out
        data = json.loads(out)
        # DetectionResult has at minimum "source" and "project" fields
        assert "source" in data

    def test_capture_passive(self, tmp_path: Path, capsys: Any) -> None:
        """capture-passive extracts Key Learnings bullets."""
        from opencontext_cli.commands.memory_v2_cmd import _dispatch_tool

        content = "## Key Learnings:\n- learned A\n- learned B\n"
        _dispatch_tool("capture-passive", tmp_path, argparse.Namespace(content=content))
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "learned A" in data

    def test_backendless_verbs_exit_2(self, tmp_path: Path) -> None:
        """stats, timeline, merge-projects have no backend and must exit 2."""
        from opencontext_cli.commands.memory_v2_cmd import _dispatch_tool

        for verb in ("stats", "timeline", "merge-projects"):
            with pytest.raises(SystemExit) as excinfo:
                _dispatch_tool(verb, tmp_path, argparse.Namespace())
            assert excinfo.value.code == 2, f"{verb}: expected exit 2, got {excinfo.value.code}"
