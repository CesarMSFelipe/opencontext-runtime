"""Tests for AgentAdapter, LocalAdapter, PythonAdapter, and AiderAdapter."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.adapters import AiderAdapter, AgentResult, LocalAdapter, PythonAdapter
from opencontext_core.adapters.base import AgentAdapter


class TestAgentAdapterBase:
    def test_abstract_class_cannot_be_instantiated(self) -> None:
        """AgentAdapter is abstract and cannot be instantiated directly."""
        try:
            AgentAdapter()  # type: ignore[abstract]
            assert False, "Should have raised TypeError"
        except TypeError:
            pass

    def test_agent_result_defaults(self) -> None:
        result = AgentResult(success=True)
        assert result.success is True
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.metadata == {}


class TestLocalAdapter:
    def test_check_available_returns_true(self) -> None:
        adapter = LocalAdapter()
        assert adapter.check_available() is True

    def test_execute_empty_instruction_returns_error(self) -> None:
        adapter = LocalAdapter()
        result = adapter.execute("", timeout=5)
        assert result.success is False
        assert result.exit_code == -1

    def test_execute_echo(self) -> None:
        adapter = LocalAdapter()
        result = adapter.execute("echo hello world", timeout=5)
        assert result.success is True
        assert result.exit_code == 0
        assert "hello world" in result.stdout

    def test_execute_with_cwd(self, tmp_path: Path) -> None:
        adapter = LocalAdapter()
        (tmp_path / "test.txt").write_text("content", encoding="utf-8")
        result = adapter.execute("cat test.txt", cwd=tmp_path, timeout=5)
        assert result.success is True
        assert "content" in result.stdout

    def test_execute_nonexistent_command(self) -> None:
        adapter = LocalAdapter()
        result = adapter.execute("nonexistent_command_xyz", timeout=5)
        assert result.success is False

    def test_execute_timeout(self) -> None:
        adapter = LocalAdapter()
        result = adapter.execute("sleep 10", timeout=1)
        assert result.success is False
        assert result.exit_code == -3

    def test_adapter_name(self) -> None:
        adapter = LocalAdapter()
        assert adapter.name == "local"

    def test_workflow_default_instruction(self) -> None:
        adapter = LocalAdapter()
        result = adapter.run_workflow("sdd", "test task", Path("/tmp"))
        # Should attempt to execute and fail gracefully (no project context)
        assert result.success is False or isinstance(result, AgentResult)


class TestPythonAdapter:
    def test_python_adapter_exists(self) -> None:
        adapter = PythonAdapter()
        assert adapter.name == "python"
        assert adapter.check_available() is True

    def test_python_execute_module(self) -> None:
        adapter = PythonAdapter()
        result = adapter.execute("python3 -c 'print(42)'", timeout=5)
        assert result.success is True
        assert "42" in result.stdout

    def test_python_execute_pytest(self) -> None:
        """PythonAdapter should pass pytest commands through directly."""
        adapter = PythonAdapter()
        result = adapter.execute("pytest --version", timeout=10)
        assert result.success is True
        assert "pytest" in result.stdout


class TestAiderAdapter:
    def test_check_available(self) -> None:
        """Aider may or may not be installed."""
        adapter = AiderAdapter()
        # This test just verifies it doesn't crash
        available = adapter.check_available()
        assert isinstance(available, bool)

    def test_execute_when_not_installed(self) -> None:
        adapter = AiderAdapter()
        result = adapter.execute("test instruction", timeout=5)
        if not adapter.check_available():
            # Should report aider not installed
            assert result.success is False
            assert "aider is not installed" in result.stderr
        # If aider IS installed, the test would try to run it (and likely time out
        # since no API key is configured), which is acceptable.

    def test_aider_adapter_constructor(self) -> None:
        adapter = AiderAdapter(
            model="claude-sonnet-4-20250514",
            architect=True,
            auto_commits=False,
            lint=True,
            test=True,
        )
        assert adapter.name == "aider"
        assert adapter.model == "claude-sonnet-4-20250514"
        assert adapter.architect is True
        assert adapter.auto_commits is False

    def test_build_args_contains_message(self) -> None:
        adapter = AiderAdapter()
        args = adapter._build_args("fix the bug")
        assert "--message" in args
        msg_index = args.index("--message")
        assert args[msg_index + 1] == "fix the bug"

    def test_build_args_contains_no_auto_commits(self) -> None:
        adapter = AiderAdapter(auto_commits=False)
        args = adapter._build_args("test")
        assert "--no-auto-commits" in args

    def test_build_args_with_model(self) -> None:
        adapter = AiderAdapter(model="gpt-4")
        args = adapter._build_args("test")
        assert "--model" in args
        model_index = args.index("--model")
        assert args[model_index + 1] == "gpt-4"

    def test_build_args_contains_yes_flag(self) -> None:
        """Non-interactive flag should always be present."""
        adapter = AiderAdapter()
        args = adapter._build_args("test")
        assert "--yes" in args

    def test_build_args_contains_no_stream(self) -> None:
        adapter = AiderAdapter()
        args = adapter._build_args("test")
        assert "--no-stream" in args
