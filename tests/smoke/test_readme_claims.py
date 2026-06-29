"""
End-to-end smoke tests that verify every quantified README claim.

Each test runs the actual CLI or Python SDK — no mocks.
If this file passes, the README is accurate.

Run:
    pytest tests/smoke/test_readme_claims.py -v
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]

# Opt-in guard for the meta-test that runs the entire suite as a subprocess.
# Without this, `pytest` over `tests/` would re-spawn the full suite from inside
# the suite — infinite recursion / fork bomb. Off by default; the child is spawned
# with the var stripped so a nested run always skips it.
_RUN_SUITE_SMOKE = "OPENCONTEXT_RUN_SUITE_SMOKE"


def cli(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run opencontext CLI and return the result."""
    return subprocess.run(
        [sys.executable, "-m", "opencontext_cli", *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )


# ── Test count ─────────────────────────────────────────────────────────────────


class TestTestCount:
    # A raw "N tests collected" assertion is circular and brittle (it breaks every
    # time a test is added or removed and proves nothing about the product). The
    # meaningful claim — "the suite passes" — is the opt-in meta-test below.
    def test_full_suite_passes(self):
        """All tests pass — no regressions. Opt-in (set OPENCONTEXT_RUN_SUITE_SMOKE=1)."""
        if not os.environ.get(_RUN_SUITE_SMOKE):
            pytest.skip(f"meta-test that runs the whole suite; set {_RUN_SUITE_SMOKE}=1 to enable")
        child_env = {k: v for k, v in os.environ.items() if k != _RUN_SUITE_SMOKE}
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--tb=short", "-q"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
            env=child_env,
        )
        assert result.returncode == 0, (
            f"Test suite failed.\n--- STDOUT ---\n{result.stdout[-2000:]}"
            f"\n--- STDERR ---\n{result.stderr[-500:]}"
        )


# ── CLI: opencontext contract build ────────────────────────────────────────────


class TestContractBuild:
    def test_contract_build_runs(self):
        """opencontext contract build returns valid YAML with required fields."""
        result = cli("contract", "build", "--query", "fix crash in auth middleware")
        assert result.returncode == 0, f"contract build failed:\n{result.stderr}"
        out = result.stdout
        assert "task:" in out
        assert "task_type:" in out
        assert "risk_tier:" in out
        assert "token_budget:" in out
        assert "must_verify:" in out

    def test_contract_risk_tiers_are_valid(self):
        """risk_tier is one of the three documented values."""
        result = cli("contract", "build", "--query", "fix crash in auth middleware")
        assert result.returncode == 0
        for line in result.stdout.splitlines():
            if line.startswith("risk_tier:"):
                tier = line.split(":")[1].strip()
                assert tier in ("cheap", "precise", "critical"), f"Unknown tier: {tier}"
                return
        pytest.fail("risk_tier not found in output")

    def test_contract_token_budget_by_tier(self):
        """Token budget matches documented tier sizes: cheap=8k, precise=16k, critical=28k."""
        expected = {"cheap": 8000, "precise": 16000, "critical": 28000}
        result = cli("contract", "build", "--query", "fix crash in auth middleware")
        assert result.returncode == 0
        lines = result.stdout.splitlines()
        tier = budget = None
        for line in lines:
            if line.startswith("risk_tier:"):
                tier = line.split(":")[1].strip()
            if line.startswith("token_budget:"):
                budget = int(line.split(":")[1].strip())
        assert tier is not None and budget is not None
        assert budget == expected[tier], (
            f"tier={tier} expected budget={expected[tier]}, got {budget}"
        )

    def test_low_risk_query_gets_cheap_tier(self):
        """Renames/trivial queries → cheap tier (8k budget)."""
        result = cli("contract", "build", "--query", "rename variable cleanup typo")
        assert result.returncode == 0
        for line in result.stdout.splitlines():
            if line.startswith("token_budget:"):
                budget = int(line.split(":")[1].strip())
                assert budget == 8000, f"Trivial task got budget {budget}, expected 8000"
                return
        pytest.fail("token_budget not found")


# ── CLI: opencontext loop --dry-run ────────────────────────────────────────────


class TestLoopDryRun:
    def test_full_flow_has_8_phases(self):
        """`opencontext loop --flow full` runs the core SDD phases.

        The CLI loop displays eight phases (explore→…→archive); the review summary
        is folded into the run, whereas the harness SDD workflow lists nine
        (…→verify→review→archive). This guards the loop CLI flow, not the harness.
        """
        result = cli("loop", "--task", "fix auth bug", "--flow", "full", "--dry-run")
        assert result.returncode == 0, f"loop --dry-run failed:\n{result.stderr}"
        phases = [
            "EXPLORE",
            "PROPOSE",
            "SPEC",
            "DESIGN",
            "TASKS",
            "APPLY",
            "VERIFY",
            "ARCHIVE",
        ]
        for phase in phases:
            assert phase in result.stdout, f"Phase {phase} missing from dry-run output"

    def test_quick_flow_has_3_phases(self):
        """README: quick = explore → apply → verify."""
        result = cli("loop", "--task", "rename x", "--flow", "quick", "--dry-run")
        assert result.returncode == 0
        assert "EXPLORE" in result.stdout
        assert "APPLY" in result.stdout
        assert "VERIFY" in result.stdout
        assert "SPEC" not in result.stdout
        assert "DESIGN" not in result.stdout

    def test_loop_blocks_without_index(self, tmp_path):
        """README: loop shows clear message when no index exists."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "opencontext_cli",
                "loop",
                "--task",
                "test",
                "--flow",
                "quick",
                "--root",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )
        assert result.returncode != 0
        out = (result.stdout + result.stderr).lower()
        assert "index" in out, f"Expected index-related message, got:\n{out}"


# ── CLI: opencontext bytecode ───────────────────────────────────────────────────


class TestBytecodeCLI:
    def test_bytecode_compile_produces_aicx(self):
        """opencontext bytecode compile outputs valid AICX/1 bytecode."""
        result = cli("bytecode", "compile", "--query", "fix auth bug")
        assert result.returncode == 0, f"bytecode compile failed:\n{result.stderr}"
        assert "AICX/1" in result.stdout
        assert "REQ" in result.stdout
        assert "TRUST" in result.stdout
        assert "CHK" in result.stdout

    def test_bytecode_compile_checksum_valid(self):
        """Bytecode checksum is always reported as valid on fresh compile."""
        result = cli("bytecode", "compile", "--query", "fix auth bug")
        assert result.returncode == 0
        assert "✓ valid" in result.stdout

    def test_bytecode_compile_reports_token_reduction(self):
        """Bytecode compile reports token reduction percentage."""
        result = cli("bytecode", "compile", "--query", "add feature to middleware")
        assert result.returncode == 0
        assert "token reduction" in result.stdout

    def test_bytecode_compile_json_flag(self):
        """--json flag outputs JSON with required fields."""
        import json

        result = cli("bytecode", "compile", "--query", "fix bug", "--json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "v" in data
        assert data["v"] == "AICX/1"
        assert "chk" in data
        assert "d" in data
        assert "i" in data

    def test_bytecode_save_and_inspect(self, tmp_path):
        """Save bytecode to file, then inspect it."""
        save_path = tmp_path / "test.aicx"
        compile_result = cli(
            "bytecode",
            "compile",
            "--query",
            "fix bug",
            "--json",
            "--save",
            str(save_path),
        )
        assert compile_result.returncode == 0
        assert save_path.exists()

        inspect_result = cli("bytecode", "inspect", str(save_path))
        assert inspect_result.returncode == 0
        assert "Version" in inspect_result.stdout
        assert "AICX/1" in inspect_result.stdout
        assert "✓" in inspect_result.stdout  # checksum valid

    def test_bytecode_decode(self, tmp_path):
        """Decode roundtrip restores query."""
        save_path = tmp_path / "roundtrip.aicx"
        cli(
            "bytecode",
            "compile",
            "--query",
            "my unique query abc",
            "--json",
            "--save",
            str(save_path),
        )
        decode_result = cli("bytecode", "decode", str(save_path))
        assert decode_result.returncode == 0
        assert "my unique query abc" in decode_result.stdout


# ── Python SDK ─────────────────────────────────────────────────────────────────


class TestPythonSDK:
    def test_build_contract_returns_contract(self):
        """README: runtime.build_contract() returns a ContextContract."""
        from opencontext_core.runtime import OpenContextRuntime

        rt = OpenContextRuntime()
        contract = rt.build_contract("fix crash in auth middleware")
        assert contract is not None
        assert hasattr(contract, "risk_tier")
        assert hasattr(contract, "token_budget")
        assert hasattr(contract, "must_verify")
        assert contract.risk_tier in ("cheap", "precise", "critical")
        assert contract.token_budget in (8000, 16000, 28000)

    def test_agent_clients_supported(self):
        """README: 'ships adapters for 20+ agent clients'."""
        from opencontext_core.configurator.adapter import iter_adapters

        count = len(list(iter_adapters()))
        assert count >= 20, f"Expected ≥20 known agent clients, got {count}"


# ── MCP tools ──────────────────────────────────────────────────────────────────


class TestMCPTools:
    # The live MCP server is opencontext_core.mcp_stdio.MCPServer (the one the CLI
    # launches). The old indexing.mcp_server.KnowledgeGraphMCPServer is dead. These
    # tests target the live server's declared tool set.
    _EXPECTED_TOOLS = frozenset(
        {
            "opencontext_search",
            "opencontext_context",
            "opencontext_callers",
            "opencontext_callees",
            "opencontext_impact",
            "opencontext_node",
            "opencontext_files",
            "opencontext_status",
            "opencontext_trace",
            "opencontext_replace_symbol_body",
            "opencontext_insert_before_symbol",
            "opencontext_insert_after_symbol",
            "opencontext_rename_symbol",
            "opencontext_run",
            "opencontext_memory_save",
            "opencontext_memory_search",
            "opencontext_memory_context",
            "opencontext_memory_judge",
            "opencontext_quality",
            # PR-013 interface tools: session step tools + workflow/profile meta
            # tools + config doctor (13 added; total 32). The README + SVG alt
            # text were updated in lockstep (test_readme_mcp_tool_count_matches_server).
            "opencontext_session_start",
            "opencontext_session_next",
            "opencontext_session_observe",
            "opencontext_session_apply",
            "opencontext_session_inspect",
            "opencontext_session_status",
            "opencontext_session_resume",
            "opencontext_session_archive",
            "opencontext_workflow_list",
            "opencontext_workflow_explain",
            "opencontext_profile_list",
            "opencontext_profile_explain",
            "opencontext_doctor",
        }
    )

    def test_mcp_tools_exist(self, tmp_path):
        """Live MCP server exposes its full documented tool set.

        The exposed tool set is the handler map (and ``server.tools``), NOT the
        default allowlist: code-write tools and ``opencontext_run`` are exposed
        but excluded from the safe default allowlist (see
        ``tests/core/test_mcp_safe_defaults.py``).
        """
        from opencontext_core.mcp_stdio import MCPServer

        server = MCPServer(db_path=tmp_path / "context_graph.db")
        names = set(server._handlers())
        assert names == set(server.tools)
        assert names == self._EXPECTED_TOOLS, f"tool set drift: {names}"
        # The safe default allowlist is a strict subset of the exposed set.
        assert set(server._default_tool_names()) < names

    def test_mcp_tool_names_match_readme(self, tmp_path):
        """Documented tool names all exist on the live server."""
        from opencontext_core.mcp_stdio import MCPServer

        server = MCPServer(db_path=tmp_path / "context_graph.db")
        for name in self._EXPECTED_TOOLS:
            assert name in server.tools, f"MCP tool {name!r} missing"

    def test_readme_mcp_tool_count_matches_server(self, tmp_path):
        """README's stated MCP tool count must equal the live server's.

        A code<->doc invariant: this is what caught (and now prevents) the drift
        where the README advertised 9 tools while the server exposed 13. The
        count is the EXPOSED tool set (handlers), not the default allowlist.
        """
        from opencontext_core.mcp_stdio import MCPServer

        n = len(MCPServer(db_path=tmp_path / "context_graph.db")._handlers())
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        assert f"{n} tools" in readme or f"{n} MCP tools" in readme, (
            f"README must state '{n} tools' or '{n} MCP tools' to match the live MCP server; "
            "update the README when the tool set changes."
        )


# ── Quality gates ───────────────────────────────────────────────────────────────


class TestQualityGates:
    # The 16 quality gates the README documents. PhaseGate is intentionally
    # excluded — it is the gate RESULT model, not a quality gate (a bare
    # "endswith('Gate')" count wrongly includes it).
    _QUALITY_GATES = frozenset(
        {
            "ApprovalRequiredForWritesGate",
            "ArtifactPersistedGate",
            "ConfidenceGate",
            "ContextPackCreatedGate",
            "FailingTestExistsGate",
            "IncludedSourcesPresentGate",
            "NoHighRiskExportsGate",
            "NoSecretLeakageGate",
            "OmissionsRecordedGate",
            "PrivacyGate",
            "ProjectIndexExistsGate",
            "ProviderPolicyPassedGate",
            "ReviewArtifactCreatedGate",
            "SecurityScanPassedGate",
            "TokenBudgetGate",
            "TraceIdCreatedGate",
        }
    )

    def test_16_quality_gates_exist_and_are_evaluable(self):
        """README: '16 quality gates'. Assert each named gate exists with an
        id + evaluate(), not just that ≥16 classes end in 'Gate'."""
        from opencontext_core.harness import gates as gates_module

        assert len(self._QUALITY_GATES) == 16
        for name in self._QUALITY_GATES:
            gate_cls = getattr(gates_module, name, None)
            assert gate_cls is not None, f"missing quality gate: {name}"
            assert isinstance(getattr(gate_cls, "id", None), str)
            assert callable(getattr(gate_cls, "evaluate", None))


# ── AICX models ────────────────────────────────────────────────────────────────


class TestAICXModels:
    def test_compile_validate_decode_roundtrip(self):
        """Core AICX roundtrip: compile → validate → decode preserves request query."""
        from pathlib import Path

        from opencontext_core.context.bytecode import AICXCompiler, AICXDecoder, AICXValidator
        from opencontext_core.retrieval.contracts import (
            EvidencePlan,
            EvidenceRequest,
            RetrievalSurface,
            TrustDecision,
        )

        request = EvidenceRequest(
            query="fix the unique_query_xyz",
            root=Path("."),
            surface=RetrievalSurface.RUNTIME,
            max_tokens=16000,
            risk_level="normal",
        )
        plan = EvidencePlan(
            request=request,
            evidence=[],
            fallback_actions=[],
            trust_decision=TrustDecision(status="sufficient", reason="ok"),
            trace_id="test",
            source_surfaces=[RetrievalSurface.RUNTIME],
        )
        bc = AICXCompiler().compile(plan)
        report = AICXValidator().validate(bc)
        assert report.passed, f"Validation failed: {report.errors}"
        assert report.checksum_valid
        decoded = AICXDecoder().decode(bc)
        assert decoded.request.query == "fix the unique_query_xyz"

    def test_aicx_result_in_verify_context(self, tmp_path):
        """VerifiedContextResult.aicx is POPULATED (not merely declared) post-index."""
        from opencontext_core.retrieval.contracts import VerifiedContextRequest
        from opencontext_core.runtime import OpenContextRuntime

        (tmp_path / "auth.py").write_text(
            "def login(user):\n    return bool(user)\n", encoding="utf-8"
        )
        runtime = OpenContextRuntime(storage_path=tmp_path / ".storage")
        runtime.index_project(tmp_path)

        result = runtime.verify_context(
            VerifiedContextRequest(query="where is login implemented?", root=tmp_path)
        )
        # The AICX side-channel must actually carry compiled bytecode, not be None.
        assert result.aicx is not None, "aicx side-channel not populated after indexing"
        assert result.aicx.get("v") == "AICX/1"
        assert result.aicx.get("chk"), "aicx checksum missing"


# ── Compression strategies ─────────────────────────────────────────────────────


class TestCompressionStrategies:
    def test_all_4_strategies_available(self):
        """README: 4 compression strategies (none/terse/compact/efficient)."""
        from opencontext_core.backends.factory import BackendFactory

        for strategy in ("none", "terse", "compact", "efficient"):
            backend = BackendFactory.create_compression_backend(strategy)
            assert backend is not None, f"Strategy {strategy!r} not available"

    def test_terse_reduces_prose(self):
        """terse strategy compresses verbose prose (phrase + word level)."""
        from opencontext_core.backends.factory import BackendFactory

        backend = BackendFactory.create_compression_backend("terse")
        text = "In order to basically just say hello, perhaps we might consider doing this."
        compressed = backend.compress(text, [])
        assert len(compressed) < len(text), "terse did not reduce length"
        # The "in order to" -> "to" phrase compression actually fired.
        assert "in order to" not in compressed.lower()

    def test_none_strategy_is_passthrough(self):
        """none strategy never modifies content."""
        from opencontext_core.backends.factory import BackendFactory

        backend = BackendFactory.create_compression_backend("none")
        text = "def authenticate(user, password): return True"
        assert backend.compress(text, []) == text

    def test_efficient_strategy_runs(self):
        """efficient strategy runs without error."""
        from opencontext_core.backends.factory import BackendFactory

        backend = BackendFactory.create_compression_backend("efficient")
        result = backend.compress("This is a function implementation service connection.", [])
        assert isinstance(result, str)
        assert len(result) > 0


# ── Benchmark numbers ──────────────────────────────────────────────────────────
#
# The README makes NO quantified token-reduction percentage claim by design.
# The old TestBenchmarkNumbers.test_benchmark_avg_reduction_above_75_pct shelled
# out to a fake comparative benchmark that scored OpenContext as a hand-curated
# answer key and never actually ran it, then asserted a fabricated "≥75% average
# reduction". That benchmark was excised (see tests/core/test_comparative_benchmark.py),
# and the honest replacement (tests/core/test_efficiency_benchmark.py) carries a
# deny-list test forbidding any `%`/claim string in its report. There is no
# percentage claim left to verify here, so the marketing assertion was removed
# rather than rewritten.
