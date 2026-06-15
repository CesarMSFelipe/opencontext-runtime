"""Tests that AgentOrchestrator.run_agent never relies on mock output live.

`_mock_agent_execution` MUST NOT be reachable from the live
run path. A live `run_agent` call must either drive the real executor
(`BaseAgent.run`) or report executor-absent — never silently return the mock
template findings.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.agents.base import AgentConfig
from opencontext_core.agents.orchestrator import AgentOrchestrator


def _write_agent(agents_dir: Path, name: str, agent_type: str) -> None:
    """Write a minimal agent profile the loader can discover.

    The loader (`list_available_agents`) reads profiles from
    ``<agents_dir>/profiles/*.yaml``.
    """
    profiles_dir = agents_dir / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    (profiles_dir / f"{name}.yaml").write_text(
        f"name: {name}\ntype: {agent_type}\nenabled: true\nobjectives:\n  - check the code\n",
        encoding="utf-8",
    )


class TestRunAgentUsesRealExecutor:
    def test_live_run_completes_when_mock_raises(self, tmp_path: Path) -> None:
        """A live phase still completes via the real executor when the mock raises.

        We patch `_mock_agent_execution` to blow up: if the live path were
        still wired to the mock, the run would error. Instead it must drive
        the real `BaseAgent.run` executor and succeed.
        """
        agents_dir = tmp_path / ".agents"
        _write_agent(agents_dir, "security-audit", "security-audit")

        orch = AgentOrchestrator(project_root=tmp_path, agents_dir=agents_dir)

        def _boom(*_a: object, **_kw: object) -> dict:
            raise AssertionError("mock path must be unreachable from the live run")

        # If the live path touches the mock at all, this raises.
        orch._mock_agent_execution = _boom  # type: ignore[method-assign]

        result = orch.run_agent("security-audit")

        # Real executor ran: status is success and findings come from the agent,
        # not the mock template ("Analyzed project using ... agent").
        assert result.status == "success"
        for finding in result.findings:
            assert "Analyzed project using" not in str(finding.get("message", ""))
        assert result.metadata.get("executor") == "real"

    def test_missing_executor_reports_absent_not_mock(self, tmp_path: Path) -> None:
        """When no real executor exists for the type, report absent — not mock."""
        agents_dir = tmp_path / ".agents"
        _write_agent(agents_dir, "ghost", "no-such-agent-type")

        orch = AgentOrchestrator(project_root=tmp_path, agents_dir=agents_dir)

        def _boom(*_a: object, **_kw: object) -> dict:
            raise AssertionError("mock path must be unreachable from the live run")

        orch._mock_agent_execution = _boom  # type: ignore[method-assign]

        # The loader keys agents by their declared type.
        result = orch.run_agent("no-such-agent-type")

        assert result.status == "error"
        assert result.error is not None
        # Reported absent, never faked as a successful mock.
        assert "Analyzed project using" not in result.report


class TestMockIsTestOnly:
    def test_mock_helper_still_callable_directly_for_tests(self, tmp_path: Path) -> None:
        """The mock helper remains directly callable (test-only), proving it was
        demoted rather than deleted — but the live path above never reaches it."""
        agents_dir = tmp_path / ".agents"
        _write_agent(agents_dir, "code-review", "code-review")
        orch = AgentOrchestrator(project_root=tmp_path, agents_dir=agents_dir)
        cfg = AgentConfig(name="code-review", type="code-review", objectives=["x"])
        data = orch._mock_agent_execution(cfg, None)
        assert "findings" in data
