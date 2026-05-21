"""Tests for CI checks system."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.quality.ci_checks import (
    CheckDefinition,
    CheckResult,
    CheckRunner,
    CheckSeverity,
    CheckStatus,
)


class TestCheckDefinition:
    """Test check definition parsing."""

    def test_from_markdown(self) -> None:
        content = """---
name: Security Review
description: Check for security issues
severity: error
files:
- "*.py"
patterns:
- "password"
auto_fix: false
---
Review this code for security issues.
"""
        check = CheckDefinition.from_markdown(content)
        assert check.name == "Security Review"
        assert check.description == "Check for security issues"
        assert check.severity == CheckSeverity.ERROR
        assert check.files == ["*.py"]
        assert check.patterns == ["password"]
        assert check.auto_fix is False
        assert "security issues" in check.prompt

    def test_to_markdown(self) -> None:
        check = CheckDefinition(
            name="Test Check",
            description="A test",
            severity=CheckSeverity.WARNING,
            files=["*.py"],
            patterns=["TODO"],
            prompt="Check for TODOs.",
        )
        md = check.to_markdown()
        assert "name: Test Check" in md
        assert "severity: warning" in md
        assert "TODO" in md
        assert "Check for TODOs." in md

    def test_invalid_markdown(self) -> None:
        with pytest.raises(ValueError, match="Invalid check format"):
            CheckDefinition.from_markdown("No frontmatter here")


class TestCheckRunner:
    """Test check runner."""

    @pytest.fixture
    def runner(self, tmp_path: Path) -> CheckRunner:
        return CheckRunner(tmp_path)

    def test_discover_checks_empty(self, runner: CheckRunner) -> None:
        assert runner.discover_checks() == []

    def test_discover_checks(self, runner: CheckRunner) -> None:
        runner.checks_dir.mkdir(parents=True)
        (runner.checks_dir / "test.md").write_text("""---
name: Test
description: Test check
severity: warning
files:
- "*.py"
patterns:
- "TODO"
---
Check for TODOs.
""")
        checks = runner.discover_checks()
        assert len(checks) == 1
        assert checks[0].name == "Test"

    def test_run_check_pass(self, runner: CheckRunner, tmp_path: Path) -> None:
        # Create a test file without the pattern
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    pass\n")

        check = CheckDefinition(
            name="TODO Check",
            description="Check for TODOs",
            severity=CheckSeverity.WARNING,
            files=["*.py"],
            patterns=["TODO"],
            prompt="Check for TODOs.",
        )

        results = runner.run_check(check, ["test.py"])
        assert len(results) == 1
        assert results[0].status == CheckStatus.PASSED

    def test_run_check_fail(self, runner: CheckRunner, tmp_path: Path) -> None:
        # Create a test file with the pattern
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    # TODO: fix this\n    pass\n")

        check = CheckDefinition(
            name="TODO Check",
            description="Check for TODOs",
            severity=CheckSeverity.WARNING,
            files=["*.py"],
            patterns=["TODO"],
            prompt="Check for TODOs.",
        )

        results = runner.run_check(check, ["test.py"])
        assert len(results) == 1
        assert results[0].status == CheckStatus.FAILED
        assert results[0].line == 2
        assert "TODO" in results[0].message

    def test_generate_report(self, runner: CheckRunner) -> None:
        results = {
            "Check 1": [
                CheckResult(
                    check_name="Check 1",
                    status=CheckStatus.PASSED,
                    severity=CheckSeverity.INFO,
                    message="All good",
                ),
            ],
            "Check 2": [
                CheckResult(
                    check_name="Check 2",
                    status=CheckStatus.FAILED,
                    severity=CheckSeverity.ERROR,
                    message="Found issue",
                    file="test.py",
                    line=1,
                ),
            ],
        }

        report = runner.generate_report(results)
        assert report["summary"]["total_checks"] == 2
        assert report["summary"]["passed"] == 1
        assert report["summary"]["failed"] == 1
        assert report["summary"]["errors"] == 1
        assert report["summary"]["success"] is False
        assert len(report["results"]) == 2

    def test_init_checks_directory(self, runner: CheckRunner) -> None:
        path = runner.init_checks_directory()
        assert path.exists()
        assert (path / "security-review.md").exists()
        assert (path / "code-quality.md").exists()
        assert (path / "documentation.md").exists()

    def test_create_check_template(self, runner: CheckRunner) -> None:
        template = runner.create_check_template("My Check", "A description")
        assert "name: My Check" in template
        assert "A description" in template
        assert "---" in template
