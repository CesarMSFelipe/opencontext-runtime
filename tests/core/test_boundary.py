"""Tests for boundary models and BoundaryService dispatch."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.adapters.boundary import (
    AdapterRequest,
    AdapterTarget,
    BoundaryResult,
    BoundaryService,
)


class TestAdapterTarget:
    def test_enum_values(self) -> None:
        assert AdapterTarget.CODEX.value == "codex"
        assert AdapterTarget.CURSOR.value == "cursor"
        assert AdapterTarget.CLAUDE_CODE.value == "claude_code"
        assert AdapterTarget.WINDSURF.value == "windsurf"
        assert AdapterTarget.OPENCODE.value == "opencode"
        assert AdapterTarget.OPENCLAW.value == "openclaw"

    def test_valid_construct(self) -> None:
        t = AdapterTarget("codex")
        assert t == AdapterTarget.CODEX


class TestAdapterRequest:
    def test_minimal_request(self) -> None:
        req = AdapterRequest(target="opencode", task="explore auth module")
        assert req.target == AdapterTarget.OPENCODE
        assert req.task == "explore auth module"
        assert req.workflow_pack is None
        assert req.root == "."
        assert req.budget_mode == "warn"

    def test_full_request(self) -> None:
        req = AdapterRequest(
            target="cursor",
            task="implement login feature",
            workflow_pack="sdd",
            root="/projects/myapp",
            budget_mode="strict",
        )
        assert req.target == AdapterTarget.CURSOR
        assert req.workflow_pack == "sdd"
        assert req.root == "/projects/myapp"
        assert req.budget_mode == "strict"

    def test_extra_fields_forbidden(self) -> None:
        import pytest

        with pytest.raises((TypeError, ValueError)):
            AdapterRequest(target="opencode", task="test", unknown_field="x")  # type: ignore[call-arg]


class TestBoundaryResult:
    def test_defaults(self) -> None:
        result = BoundaryResult(success=True, target="opencode")
        assert result.success is True
        assert result.target == "opencode"
        assert result.run_id is None
        assert result.phases == []
        assert result.gates == []
        assert result.warnings == []
        assert result.error is None

    def test_with_error(self) -> None:
        result = BoundaryResult(success=False, target="cursor", error="something broke")
        assert result.success is False
        assert result.error == "something broke"


class TestBoundaryService:
    def test_generic_dispatch_unknown_target(self) -> None:
        service = BoundaryService()
        req = AdapterRequest(target="cursor", task="test task")
        result = service.dispatch(req)
        assert result.target == "cursor"
        assert result.success is True

    def test_opencode_dispatch_runs_workflow(self, tmp_path: Path) -> None:
        """OpenCode target should auto-wrap with sdd workflow."""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        service = BoundaryService(root=tmp_path)
        req = AdapterRequest(
            target="opencode",
            task="test sdd flow",
            root=str(tmp_path),
            budget_mode="off",
        )
        result = service.dispatch(req)
        assert result.target == "opencode"
        assert result.run_id is not None
        assert result.run_id.startswith("sdd-")

    def test_explicit_workflow_dispatch(self, tmp_path: Path) -> None:
        """Direct workflow_pack should run the named workflow."""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        service = BoundaryService(root=tmp_path)
        req = AdapterRequest(
            target="cursor",
            task="test explicit workflow",
            workflow_pack="explore-only",
            root=str(tmp_path),
            budget_mode="off",
        )
        result = service.dispatch(req)
        assert result.success is True
        # explore-only should produce at least one phase
        assert len(result.phases) >= 1

    def test_workflow_dispatch_with_strict_budget(self, tmp_path: Path) -> None:
        """Strict mode with no project should fail gracefully."""
        service = BoundaryService(root=tmp_path)
        req = AdapterRequest(
            target="opencode",
            task="fail test",
            workflow_pack="explore-only",
            root=str(tmp_path),
            budget_mode="strict",
        )
        result = service.dispatch(req)
        # In strict mode with missing project manifest, should still return a result
        assert result.success is False or result.run_id is not None

    def test_boundary_service_default_root(self) -> None:
        service = BoundaryService()
        assert service.root is not None
        assert isinstance(service.root, Path)
