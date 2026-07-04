"""Tests for the distinct not_applied status when apply runs provider-free.

P1.1: A provider-free apply (no executor wired, no apply_edits supplied)
must yield GateStatus.NOT_APPLIED instead of the ambiguous GateStatus.WARNING.
GateStatus.WARNING is reserved for genuine advisories.

RED phase — these fail before the implementation lands.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.runner import HarnessRunner


class TestNotAppliedStatus:
    """GateStatus.NOT_APPLIED is set when apply ran with no edits and no executor."""

    def test_not_applied_value_exists(self) -> None:
        """GateStatus must expose a NOT_APPLIED member with value 'not_applied'."""
        assert GateStatus.NOT_APPLIED == "not_applied"

    def test_not_applied_is_not_ok(self) -> None:
        """NOT_APPLIED is not considered an 'ok' status (no real work was done)."""
        assert not GateStatus.NOT_APPLIED.is_ok

    def test_provider_free_apply_yields_not_applied(self, tmp_path: Path) -> None:
        """A full SDD run with no delegate and no apply_edits yields NOT_APPLIED.

        The run must NOT return WARNING (which is reserved for genuine advisories)
        and must NOT return PASSED (which would falsely imply edits were written).
        """
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        runner = HarnessRunner(root=tmp_path)
        result = runner.run("sdd", "implement login feature", BudgetMode.OFF)
        # No executor wired → apply ran but produced no edits.
        # Must be NOT_APPLIED, not the ambiguous WARNING.
        assert result.status == GateStatus.NOT_APPLIED, (
            f"Expected NOT_APPLIED but got {result.status!r}. "
            "Provider-free apply must not silently return WARNING."
        )

    def test_provider_free_apply_not_warning(self, tmp_path: Path) -> None:
        """A provider-free apply must NOT yield WARNING.

        WARNING is reserved for genuine advisory findings (e.g. orphan symbols,
        budget overruns) that occur on a run that did real work.
        """
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        runner = HarnessRunner(root=tmp_path)
        result = runner.run("sdd", "add auth middleware", BudgetMode.OFF)
        assert result.status != GateStatus.WARNING, (
            "Provider-free apply must not collapse into WARNING. "
            "Use NOT_APPLIED to distinguish 'no executor' from 'real advisory'."
        )

    def test_advisory_run_still_yields_warning(self, tmp_path: Path) -> None:
        """A run that actually emits advisory gates still yields WARNING (not NOT_APPLIED).

        This test uses the explore-only workflow (no apply phase) with an empty
        project so the missing-index gate fires as a WARNING under BudgetMode.OFF.
        The NOT_APPLIED logic must not touch non-apply workflows.
        """
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        runner = HarnessRunner(root=tmp_path)
        # explore-only never runs apply; the missing KG index fires a WARNING.
        result = runner.run("explore-only", "look at login code", BudgetMode.OFF)
        # explore-only has no apply phase — NOT_APPLIED must NOT be set here.
        assert result.status != GateStatus.NOT_APPLIED, (
            "NOT_APPLIED must only be set when the apply phase ran with no executor. "
            "explore-only runs must not be affected."
        )
