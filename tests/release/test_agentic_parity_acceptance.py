"""25-point agentic-parity acceptance tests.

Per openspec/changes/agentic-parity-engram-gentle/proposal.md §Success Criteria
(#1–#25). Each named test maps to one success criterion for the full change.
"""

from __future__ import annotations

import importlib
from pathlib import Path


class TestSDDPackageSurface:
    """#1–#8: opencontext_sdd package surface."""

    def test_01_status_model_exported(self) -> None:
        from opencontext_sdd import Status
        assert Status is not None

    def test_02_resolve_function_exported(self) -> None:
        from opencontext_sdd import Resolve
        assert callable(Resolve)

    def test_03_dispatcher_markdown_exported(self) -> None:
        from opencontext_sdd import RenderDispatcherMarkdown
        assert callable(RenderDispatcherMarkdown)

    def test_04_skill_registry_refresh_exported(self) -> None:
        from opencontext_sdd import refresh_skill_registry
        assert callable(refresh_skill_registry)

    def test_05_catalog_exported(self) -> None:
        from opencontext_sdd import Catalog
        assert Catalog is not None

    def test_06_runner_phase_result_exported(self) -> None:
        from opencontext_sdd import PhaseResultEnvelope
        assert PhaseResultEnvelope is not None

    def test_07_overlay_sub_agent_count(self) -> None:
        from opencontext_sdd.overlay import SDD_OVERLAY_MULTI
        agents = SDD_OVERLAY_MULTI.get("agents", {})
        assert len(agents) == 8

    def test_08_phase_list_correct_order(self) -> None:
        from opencontext_sdd.runner import Orchestrator
        orch = Orchestrator(cwd=Path("."), change="test")
        assert orch._phases == ("explore", "propose", "spec", "design",
                                 "tasks", "apply", "verify", "archive")


class TestMemoryPackageSurface:
    """#9–#16: opencontext_memory package surface."""

    def test_09_memory_store_exported(self) -> None:
        from opencontext_memory import MemoryStore
        assert MemoryStore is not None

    def test_10_mem_save_exported(self) -> None:
        from opencontext_memory import mem_save
        assert callable(mem_save)

    def test_11_mem_search_exported(self) -> None:
        from opencontext_memory import mem_search
        assert callable(mem_search)

    def test_12_mem_context_exported(self) -> None:
        from opencontext_memory import mem_context
        assert callable(mem_context)

    def test_13_mem_session_summary_exported(self) -> None:
        from opencontext_memory import mem_session_summary
        assert callable(mem_session_summary)

    def test_14_detect_project_full_exported(self) -> None:
        from opencontext_memory import DetectProjectFull
        assert callable(DetectProjectFull)

    def test_15_lifecycle_state_exported(self) -> None:
        from opencontext_memory import state
        assert callable(state)

    def test_16_models_exported(self) -> None:
        from opencontext_memory import MemoryRecord, SaveReceipt, ConflictEnvelope
        assert MemoryRecord is not None
        assert SaveReceipt is not None


class TestCLISurface:
    """#17–#20: CLI commands."""

    def test_17_sdd_cli_registered(self) -> None:
        from opencontext_cli.main import _build_parser
        p = _build_parser()
        a = p.parse_args(["sdd", "status", "--change", "test", "--cwd", "."])
        assert a.sdd_command == "status"

    def test_18_memory_v2_cli_registered(self) -> None:
        from opencontext_cli.main import _build_parser
        p = _build_parser()
        a = p.parse_args(["memory", "v2", "save", "--title", "test"])
        assert a.v2_command == "save"

    def test_19_agent_harness_cli_registered(self) -> None:
        from opencontext_cli.main import _build_parser
        p = _build_parser()
        a = p.parse_args(["agent-harness", "acceptance", "--root", "."])
        assert a.agent_harness_command == "acceptance"

    def test_20_help_invocation_succeeds(self) -> None:
        import subprocess, sys
        r = subprocess.run([sys.executable, "-m", "opencontext_cli", "--help"],
                           capture_output=True, text=True, timeout=15)
        assert r.returncode == 0


class TestAPISurface:
    """#21–#23: FastAPI routes."""

    def test_21_memory_api_routes_registered(self) -> None:
        from opencontext_api.main import app
        routes = {r.path for r in app.routes}
        assert "/v1/memory/save" in routes

    def test_22_sdd_api_routes_registered(self) -> None:
        from opencontext_api.main import app
        routes = {r.path for r in app.routes}
        assert "/v1/sdd/status" in routes

    def test_23_memory_api_search_works(self) -> None:
        from fastapi.testclient import TestClient
        from opencontext_api.main import app
        client = TestClient(app)
        resp = client.get("/v1/memory/search?query=test")
        assert resp.status_code == 200


class TestReleaseGates:
    """#24–#25: Release gates."""

    def test_24_no_coauthored_by_trailers(self) -> None:
        import subprocess
        result = subprocess.run(
            ["git", "log", "-10", "--format=%B%n---"],
            capture_output=True, text=True, timeout=15,
        )
        assert "Co-Authored-By" not in result.stdout

    def test_25_pytest_passes_sdd_and_memory(self) -> None:
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-m", "pytest",
             "packages/opencontext_sdd/tests/",
             "packages/opencontext_memory/tests/",
             "-q", "--tb=line"],
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, f"pytest stderr:\n{result.stderr}"
