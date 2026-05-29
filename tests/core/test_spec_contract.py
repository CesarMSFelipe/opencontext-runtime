"""Tests for spec contract (SpecKernel + validate_spec)."""

from __future__ import annotations

from opencontext_core.agents.spec_contract import SpecKernel, validate_spec


class TestSpecKernel:
    """Test SpecKernel construction."""

    def test_all_fields_provided(self) -> None:
        kernel = SpecKernel(
            why="Need to validate specs",
            capabilities=["Validate fields"],
            constraints=["Must be fast"],
            non_goals=["No auto-fix"],
            success_signals=["No warnings"],
        )
        assert kernel.why == "Need to validate specs"
        assert kernel.capabilities == ["Validate fields"]
        assert kernel.constraints == ["Must be fast"]
        assert kernel.non_goals == ["No auto-fix"]
        assert kernel.success_signals == ["No warnings"]

    def test_fields_accessible_as_attributes(self) -> None:
        kernel = SpecKernel(why="test")
        assert kernel.why == "test"
        assert kernel.capabilities == []
        assert kernel.constraints == []


class TestValidateSpec:
    """Test validate_spec warnings."""

    def test_all_fields_populated_returns_empty(self) -> None:
        kernel = SpecKernel(
            why="Reason",
            capabilities=["cap1"],
            constraints=["con1"],
            non_goals=["ng1"],
            success_signals=["sig1"],
        )
        warnings = validate_spec(kernel)
        assert warnings == []

    def test_missing_non_goals_returns_one_warning(self) -> None:
        kernel = SpecKernel(
            why="Reason",
            capabilities=["cap1"],
            constraints=["con1"],
            success_signals=["sig1"],
        )
        warnings = validate_spec(kernel)
        assert len(warnings) == 1
        assert "non_goals" in warnings[0]

    def test_missing_two_fields_returns_two_warnings(self) -> None:
        kernel = SpecKernel(
            why="Reason",
            capabilities=["cap1"],
        )
        warnings = validate_spec(kernel)
        assert len(warnings) == 3  # constraints, non_goals, success_signals
        assert all("missing" in w for w in warnings)

    def test_empty_kernel_returns_five_warnings(self) -> None:
        kernel = SpecKernel()
        warnings = validate_spec(kernel)
        assert len(warnings) == 5
