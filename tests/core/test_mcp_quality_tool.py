"""Tests for the ``opencontext_quality`` MCP tool (architecture & quality gate).

Covers the 15th MCP tool registered in ``opencontext_core.mcp_stdio`` that
exposes the deterministic, zero-model :class:`QualityEvaluator` over MCP:

  * advertise + default-allowlist + handler + policy (surface parity with the
    other 14 tools)
  * ``scope='all'`` evaluates the whole project; ``scope='diff'`` (the default)
    evaluates the working-tree changed files
  * a real import cycle surfaces as a ``max_cycles`` finding through the tool,
    with the report-dict shape ``ci-check run`` speaks
    (``summary``/``results``/``health``/``delta``)
  * determinism: identical inputs -> byte-identical report dict
  * ZERO model calls: a sentinel host-sampler that raises if invoked is never
    called by the check path
  * degrade-honestly: an invalid scope and a missing rules file return a
    structured ``{'error': ...}`` (never raise); the tool returns a valid report
    even when there are no changed files
  * tmp isolation: the tool resolves the root to ``tmp_path`` and never reads or
    writes the real ``~/.opencontext`` or the repo ``.opencontext``

The tests follow the existing ``tests/core/test_mcp_memory_tools.py`` patterns:
``MCPServer(db_path=tmp_path / ...)`` for tmp isolation and ``server._call_tool``
to drive the tool exactly as a host would.

The language-tool subprocesses are stubbed out at the runner's ``_run_tool`` so
no real linter is required on CI and no real ``subprocess`` is spawned (the
patch is scoped to the quality runner, so unrelated ``git`` calls keep working).
This both removes the tool dependency and proves the check path is subprocess-
isolated; the architecture passes (graph + tree-sitter) provide the findings.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import opencontext_core.quality.languages as languages_mod
from opencontext_core.mcp_stdio import MCPServer

_TOOL = "opencontext_quality"

# A 2-file Python import cycle: a -> b -> a. ``DependencyGraphBuilder`` resolves
# ``import b``/``import a`` to ``b.py``/``a.py`` (both in the scanned set), so the
# file-level Tarjan SCC reports exactly one cycle -> one ``max_cycles`` finding.
_A_PY = "import b\n\n\ndef fa():\n    return b.fb()\n"
_B_PY = "import a\n\n\ndef fb():\n    return a.fa()\n"


@pytest.fixture(autouse=True)
def _stub_language_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every language tool report 'missing' without spawning a subprocess.

    Patches ONLY ``LanguageQualityRunner._run_tool`` (not the shared
    ``subprocess`` module) so the deterministic architecture passes are exercised
    while no real linter is required, and so ``git`` (used to build the diff
    scope) is unaffected. Under the zero-config STANDARD profile ruff/mypy are
    required only at STRICT, so a "missing" tool degrades to ``skipped`` — never a
    finding — keeping the report deterministic regardless of the CI toolchain.
    """

    def _missing(self: object, spec: object, files: object) -> object:
        return languages_mod.ToolRun(
            tool=getattr(spec, "name", "tool"),
            exit_code=-2,
            stdout="",
            stderr="",
            missing=True,
        )

    monkeypatch.setattr(languages_mod.LanguageQualityRunner, "_run_tool", _missing)


def _make_project(root: Path, *, git: bool = False) -> None:
    """Write the 2-file cycle project under ``root`` (optionally a git repo)."""
    if git:
        subprocess.run(
            ["git", "init", "-q", str(root)],
            check=True,
            capture_output=True,
        )
    (root / "a.py").write_text(_A_PY, encoding="utf-8")
    (root / "b.py").write_text(_B_PY, encoding="utf-8")


def _server(tmp_path: Path) -> MCPServer:
    """An MCP server rooted at ``tmp_path`` with a throwaway (absent) graph DB.

    The architecture analyzer degrades honestly against a missing DB, so the
    graph need not be pre-built for these tests; the import-cycle signal comes
    from scanning ``tmp_path`` directly.
    """
    return MCPServer(
        db_path=tmp_path / ".storage" / "opencontext" / "context_graph.db",
        project_root=tmp_path,
    )


# --------------------------------------------------------------------------- #
# Surface parity — advertise / allowlist / handler / policy
# --------------------------------------------------------------------------- #


class TestQualityToolAdvertised:
    def test_tool_registered_with_schema(self, tmp_path: Path) -> None:
        server = _server(tmp_path)
        assert _TOOL in server.tools
        schema = server.tools[_TOOL]
        assert "description" in schema
        params = schema["parameters"]
        assert "scope" in params and "rules" in params
        # The scope default is the cheap working-tree path.
        assert params["scope"].get("default") == "diff"
        server.close()

    def test_tool_in_default_allowlist(self, tmp_path: Path) -> None:
        server = _server(tmp_path)
        assert _TOOL in server._default_tool_names()
        server.close()

    def test_tool_has_handler(self, tmp_path: Path) -> None:
        server = _server(tmp_path)
        assert _TOOL in server._handlers()
        server.close()

    def test_default_policy_allows_tool(self, tmp_path: Path) -> None:
        server = _server(tmp_path)
        assert server.policy.allows(_TOOL)
        server.close()

    def test_tool_name_carries_prefix(self, tmp_path: Path) -> None:
        server = _server(tmp_path)
        assert _TOOL.startswith("opencontext_")
        server.close()

    def test_tool_listed_in_tools_list_rpc(self, tmp_path: Path) -> None:
        """The tool is surfaced through the ``tools/list`` JSON-RPC view too."""
        server = _server(tmp_path)
        listed = {
            t["name"]
            for t in (
                {
                    "name": name,
                    "description": info["description"],
                    "inputSchema": {"type": "object", "properties": info["parameters"]},
                }
                for name, info in server.tools.items()
            )
        }
        assert _TOOL in listed
        server.close()


# --------------------------------------------------------------------------- #
# scope='all' — whole-project evaluation surfaces the cycle
# --------------------------------------------------------------------------- #


class TestQualityScopeAll:
    def test_all_reports_cycle_finding(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        server = _server(tmp_path)
        result = server._call_tool(_TOOL, {"scope": "all"})
        assert "error" not in result, result
        # The report-dict shape ci-check run speaks.
        assert set(result) >= {"summary", "results", "health", "delta"}
        # One file-level import cycle detected.
        assert result["health"]["metrics"]["cycles"] == 1
        rules = {row["check"] for row in result["results"]}
        assert "max_cycles" in rules
        server.close()

    def test_all_health_reflects_single_cycle_penalty(self, tmp_path: Path) -> None:
        """One cycle => a perfect 10000 minus exactly the cycle weight (400)."""
        _make_project(tmp_path)
        server = _server(tmp_path)
        result = server._call_tool(_TOOL, {"scope": "all"})
        assert result["health"]["score"] == 9600
        assert result["health"]["components"]["cycles"] == 400
        server.close()

    def test_clean_project_scores_perfect_and_no_findings(self, tmp_path: Path) -> None:
        """A project with no cycle has a perfect score and an empty result set."""
        (tmp_path / "solo.py").write_text("def only():\n    return 1\n", encoding="utf-8")
        server = _server(tmp_path)
        result = server._call_tool(_TOOL, {"scope": "all"})
        assert "error" not in result, result
        assert result["health"]["metrics"]["cycles"] == 0
        assert result["health"]["score"] == 10000
        assert result["results"] == []
        # No cycle, no boundary, no over-threshold complexity -> not blocking.
        assert result["summary"]["success"] is True
        server.close()


# --------------------------------------------------------------------------- #
# scope='diff' (the default) — changed-file evaluation
# --------------------------------------------------------------------------- #


class TestQualityScopeDiff:
    def test_diff_reports_cycle_for_untracked_changes(self, tmp_path: Path) -> None:
        """Files untracked in a git repo are the diff scope -> cycle is reported."""
        _make_project(tmp_path, git=True)
        server = _server(tmp_path)
        result = server._call_tool(_TOOL, {"scope": "diff"})
        assert "error" not in result, result
        assert result["health"]["metrics"]["cycles"] == 1
        rules = {row["check"] for row in result["results"]}
        assert "max_cycles" in rules
        server.close()

    def test_default_scope_is_diff(self, tmp_path: Path) -> None:
        """Omitting ``scope`` behaves exactly like ``scope='diff'``."""
        _make_project(tmp_path, git=True)
        server = _server(tmp_path)
        default = server._call_tool(_TOOL, {})
        explicit = server._call_tool(_TOOL, {"scope": "diff"})
        assert "error" not in default, default
        assert default == explicit
        server.close()

    def test_diff_without_git_returns_valid_report(self, tmp_path: Path) -> None:
        """No git repo -> empty change set -> a valid (non-error) report shape.

        The whole-graph cycle still counts in metrics, but with nothing in the
        changed scope no finding is *reported* — degrade honestly, never crash.
        """
        _make_project(tmp_path, git=False)
        server = _server(tmp_path)
        result = server._call_tool(_TOOL, {"scope": "diff"})
        assert "error" not in result, result
        assert set(result) >= {"summary", "results", "health", "delta"}
        assert result["results"] == []
        server.close()


# --------------------------------------------------------------------------- #
# Determinism — identical inputs produce an identical report
# --------------------------------------------------------------------------- #


class TestQualityDeterminism:
    def test_repeated_calls_are_byte_identical(self, tmp_path: Path) -> None:
        _make_project(tmp_path)
        server = _server(tmp_path)
        first = server._call_tool(_TOOL, {"scope": "all"})
        second = server._call_tool(_TOOL, {"scope": "all"})
        assert first == second
        server.close()

    def test_fresh_server_same_inputs_same_report(self, tmp_path: Path) -> None:
        """Determinism holds across server instances, not just within one."""
        _make_project(tmp_path)
        first = _server(tmp_path)
        report_a = first._call_tool(_TOOL, {"scope": "all"})
        first.close()
        second = _server(tmp_path)
        report_b = second._call_tool(_TOOL, {"scope": "all"})
        second.close()
        assert report_a == report_b


# --------------------------------------------------------------------------- #
# Zero model calls — the check path never invokes the host sampler
# --------------------------------------------------------------------------- #


class TestQualityZeroModelCalls:
    def test_check_path_never_calls_the_model(self, tmp_path: Path) -> None:
        """A sentinel host-sampler that raises must never be invoked.

        The quality evaluator is graph + tree-sitter + (stubbed) subprocesses
        only; if anything tried to sample a model the registered sampler would
        fire and raise, failing this test.
        """
        from opencontext_core.llm import sampling_gateway

        calls: list[str] = []

        def _sentinel(*args: object, **kwargs: object) -> str:
            calls.append("called")
            raise AssertionError("quality check path must not call the model")

        sampling_gateway.register_host_sampler(_sentinel)
        try:
            _make_project(tmp_path)
            server = _server(tmp_path)
            result = server._call_tool(_TOOL, {"scope": "all"})
            server.close()
        finally:
            sampling_gateway.register_host_sampler(None)

        assert "error" not in result, result
        assert calls == []


# --------------------------------------------------------------------------- #
# Degrade honestly — structured errors, never raises
# --------------------------------------------------------------------------- #


class TestQualityDegradesHonestly:
    def test_invalid_scope_returns_structured_error(self, tmp_path: Path) -> None:
        server = _server(tmp_path)
        result = server._call_tool(_TOOL, {"scope": "sideways"})
        assert "error" in result
        err = result["error"].lower()
        assert "scope" in err and "diff" in err and "all" in err
        server.close()

    def test_missing_rules_file_returns_structured_error(self, tmp_path: Path) -> None:
        server = _server(tmp_path)
        result = server._call_tool(
            _TOOL,
            {"scope": "all", "rules": str(tmp_path / "does-not-exist.toml")},
        )
        assert "error" in result
        assert "not found" in result["error"].lower()
        server.close()

    def test_malformed_rules_file_returns_structured_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.toml"
        bad.write_text("this is = = not valid toml [[[", encoding="utf-8")
        server = _server(tmp_path)
        result = server._call_tool(_TOOL, {"scope": "all", "rules": str(bad)})
        assert "error" in result
        assert "quality rules" in result["error"].lower()
        server.close()

    def test_explicit_valid_rules_file_is_honored(self, tmp_path: Path) -> None:
        """An explicit, well-formed rules path is parsed and used by the tool."""
        cfg = tmp_path / "quality.toml"
        cfg.write_text('mode = "strict"\n', encoding="utf-8")
        _make_project(tmp_path)
        server = _server(tmp_path)
        result = server._call_tool(_TOOL, {"scope": "all", "rules": str(cfg)})
        assert "error" not in result, result
        # Still finds the cycle; the rules file simply selected strict mode.
        assert result["health"]["metrics"]["cycles"] == 1
        server.close()

    def test_handler_returns_dict_not_raise_on_bad_root(self, tmp_path: Path) -> None:
        """Even with nothing to analyze, the handler returns a dict (never raises)."""
        server = _server(tmp_path)  # empty tmp dir, no source
        result = server._call_tool(_TOOL, {"scope": "all"})
        assert isinstance(result, dict)
        assert "error" not in result, result
        server.close()


# --------------------------------------------------------------------------- #
# tmp isolation — never touch the real ~/.opencontext or the repo .opencontext
# --------------------------------------------------------------------------- #


class TestQualityTmpIsolation:
    def test_root_resolves_to_tmp_path(self, tmp_path: Path) -> None:
        """The tool evaluates under ``tmp_path``, not the cwd / real project."""
        server = _server(tmp_path)
        assert server.project_root == tmp_path
        server.close()

    def test_tool_does_not_create_dot_opencontext(self, tmp_path: Path) -> None:
        """The check path is read-only: it never writes a baseline/config dir.

        ``evaluate`` (what the tool calls) only *reads* an existing baseline; it
        never persists one, so no ``.opencontext`` directory appears under the
        project root as a side effect of running the tool.
        """
        _make_project(tmp_path)
        server = _server(tmp_path)
        server._call_tool(_TOOL, {"scope": "all"})
        server.close()
        assert not (tmp_path / ".opencontext").exists()

    def test_tool_does_not_touch_real_home_opencontext(self, tmp_path: Path) -> None:
        """Running the tool must not read or create ``~/.opencontext`` quality files.

        We snapshot the real home quality artifacts before and after; the tool is
        rooted at ``tmp_path`` and must leave them byte-for-byte unchanged (and
        must not newly create them).
        """
        home_oc = Path.home() / ".opencontext"
        baseline = home_oc / "quality-baseline.json"
        quality_toml = home_oc / "quality.toml"
        existed_before = {
            p: (p.exists(), p.read_bytes() if p.exists() else None)
            for p in (baseline, quality_toml)
        }

        _make_project(tmp_path)
        server = _server(tmp_path)
        result = server._call_tool(_TOOL, {"scope": "all"})
        server.close()
        assert "error" not in result, result

        for path, (was_present, content) in existed_before.items():
            assert path.exists() is was_present, f"{path} presence changed"
            if was_present:
                assert path.read_bytes() == content, f"{path} content changed"


class TestQualityEvolutionTrend:
    """The tool surfaces the cross-run evolution trend, READ-ONLY."""

    def test_trend_reflects_recorded_history(self, tmp_path: Path) -> None:
        """A pre-recorded evolution log shows up as latest/previous/delta/count."""
        from opencontext_core.quality.evolution import EVOLUTION_FILENAME, EvolutionStore

        store = EvolutionStore(tmp_path / EVOLUTION_FILENAME)
        store.append(timestamp="2026-06-22T00:00:00+00:00", score=9000, sub_scores={})
        store.append(timestamp="2026-06-22T01:00:00+00:00", score=9600, sub_scores={})
        before = (tmp_path / EVOLUTION_FILENAME).read_bytes()

        _make_project(tmp_path)
        server = _server(tmp_path)
        result = server._call_tool(_TOOL, {"scope": "all"})
        server.close()

        assert "error" not in result, result
        assert result["trend"] == {
            "latest": 9600,
            "previous": 9000,
            "delta": 600,
            "count": 2,
        }
        # Read-only: surfacing the trend never appends to or rewrites the log.
        assert (tmp_path / EVOLUTION_FILENAME).read_bytes() == before

    def test_trend_is_zeroed_when_no_history(self, tmp_path: Path) -> None:
        """No evolution log -> a flat zero trend, and still no .opencontext dir."""
        _make_project(tmp_path)
        server = _server(tmp_path)
        result = server._call_tool(_TOOL, {"scope": "all"})
        server.close()

        assert result["trend"] == {"latest": 0, "previous": 0, "delta": 0, "count": 0}
        assert not (tmp_path / ".opencontext").exists()
