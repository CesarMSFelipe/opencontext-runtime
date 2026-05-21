"""CI check system for automated code reviews.

Provides a framework for defining, running, and reporting checks
that can be executed in CI pipelines or locally before pushing.

Checks are defined as markdown files with a YAML frontmatter header.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class CheckSeverity(StrEnum):
    """Severity level for a check result."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class CheckStatus(StrEnum):
    """Status of a check run."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class CheckResult:
    """Result of running a single check."""

    check_name: str
    status: CheckStatus
    severity: CheckSeverity
    message: str
    file: str | None = None
    line: int | None = None
    suggestion: str | None = None
    diff: str | None = None


@dataclass
class CheckDefinition:
    """Definition of a CI check loaded from a markdown file."""

    name: str
    description: str
    severity: CheckSeverity
    files: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    prompt: str = ""
    auto_fix: bool = False

    @classmethod
    def from_markdown(cls, content: str) -> "CheckDefinition":
        """Parse a check definition from markdown content.

        Expected format:
        ---
        name: Security Review
        description: Review for security issues
        severity: error
        files: ["*.py", "*.js"]
        patterns: ["password", "secret", "token"]
        auto_fix: false
        ---
        Review this code for security issues...
        """
        # Extract YAML frontmatter
        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
        if not frontmatter_match:
            raise ValueError("Invalid check format: missing YAML frontmatter")

        import yaml

        meta = yaml.safe_load(frontmatter_match.group(1))
        prompt = frontmatter_match.group(2).strip()

        return cls(
            name=meta.get("name", "Unnamed Check"),
            description=meta.get("description", ""),
            severity=CheckSeverity(meta.get("severity", "warning")),
            files=meta.get("files", []),
            patterns=meta.get("patterns", []),
            prompt=prompt,
            auto_fix=meta.get("auto_fix", False),
        )

    def to_markdown(self) -> str:
        """Serialize check definition to markdown."""
        import yaml

        meta = {
            "name": self.name,
            "description": self.description,
            "severity": self.severity.value,
            "files": self.files,
            "patterns": self.patterns,
            "auto_fix": self.auto_fix,
        }
        frontmatter = yaml.dump(meta, default_flow_style=False, sort_keys=False)
        return f"---\n{frontmatter}---\n{self.prompt}\n"


class CheckRunner:
    """Runs CI checks against code files.

    Supports pattern-based checks that scan files for forbidden patterns
    and can be extended with LLM-powered checks.
    """

    CHECKS_DIR = Path(".opencontext/checks")

    def __init__(self, project_path: str | Path = ".") -> None:
        self.project_path = Path(project_path)
        self.checks_dir = self.project_path / self.CHECKS_DIR

    def discover_checks(self) -> list[CheckDefinition]:
        """Discover all check definitions in the checks directory."""
        if not self.checks_dir.exists():
            return []

        checks: list[CheckDefinition] = []
        for file_path in self.checks_dir.glob("*.md"):
            try:
                content = file_path.read_text()
                check = CheckDefinition.from_markdown(content)
                checks.append(check)
            except Exception:
                continue

        return checks

    def run_check(self, check: CheckDefinition, files: list[str] | None = None) -> list[CheckResult]:
        """Run a single check against the project."""
        results: list[CheckResult] = []

        # Determine files to check
        target_files = files or self._find_matching_files(check)

        for file_path in target_files:
            path = self.project_path / file_path
            if not path.exists():
                continue

            try:
                content = path.read_text()
            except Exception:
                continue

            # Run pattern checks
            for pattern in check.patterns:
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    # Get line number
                    line_num = content[:match.start()].count("\n") + 1

                    results.append(
                        CheckResult(
                            check_name=check.name,
                            status=CheckStatus.FAILED,
                            severity=check.severity,
                            message=f"Found forbidden pattern: '{pattern}'",
                            file=file_path,
                            line=line_num,
                            suggestion=f"Review usage of '{pattern}' for compliance",
                        )
                    )

        # If no failures, report success
        if not results and check.patterns:
            results.append(
                CheckResult(
                    check_name=check.name,
                    status=CheckStatus.PASSED,
                    severity=CheckSeverity.INFO,
                    message=f"All checks passed for '{check.name}'",
                )
            )

        return results

    def run_all_checks(self, files: list[str] | None = None) -> dict[str, list[CheckResult]]:
        """Run all discovered checks."""
        checks = self.discover_checks()
        results: dict[str, list[CheckResult]] = {}

        for check in checks:
            results[check.name] = self.run_check(check, files)

        return results

    def _find_matching_files(self, check: CheckDefinition) -> list[str]:
        """Find files matching the check's file patterns."""
        if not check.files:
            # Default to common source files
            check.files = ["*.py", "*.js", "*.ts", "*.jsx", "*.tsx", "*.java", "*.go", "*.rs"]

        matched: set[str] = set()
        for pattern in check.files:
            for path in self.project_path.rglob(pattern):
                # Skip common ignored directories
                parts = path.parts
                if any(
                    ignored in parts
                    for ignored in [".git", "node_modules", ".venv", "venv", "__pycache__", ".opencontext"]
                ):
                    continue
                matched.add(str(path.relative_to(self.project_path)))

        return sorted(matched)

    def generate_report(self, results: dict[str, list[CheckResult]]) -> dict[str, Any]:
        """Generate a summary report of check results."""
        total_checks = len(results)
        passed = 0
        failed = 0
        warnings = 0
        errors = 0

        all_results: list[dict[str, Any]] = []
        for check_name, check_results in results.items():
            check_passed = all(r.status == CheckStatus.PASSED for r in check_results)
            if check_passed:
                passed += 1
            else:
                failed += 1

            for r in check_results:
                if r.severity == CheckSeverity.ERROR or r.severity == CheckSeverity.CRITICAL:
                    errors += 1
                elif r.severity == CheckSeverity.WARNING:
                    warnings += 1

                all_results.append({
                    "check": r.check_name,
                    "status": r.status.value,
                    "severity": r.severity.value,
                    "message": r.message,
                    "file": r.file,
                    "line": r.line,
                    "suggestion": r.suggestion,
                })

        return {
            "summary": {
                "total_checks": total_checks,
                "passed": passed,
                "failed": failed,
                "warnings": warnings,
                "errors": errors,
                "success": failed == 0,
            },
            "results": all_results,
        }

    def create_check_template(self, name: str, description: str) -> str:
        """Create a template check definition."""
        check = CheckDefinition(
            name=name,
            description=description,
            severity=CheckSeverity.WARNING,
            files=["*.py"],
            patterns=["TODO", "FIXME"],
            prompt="Review this code for issues.",
        )
        return check.to_markdown()

    def init_checks_directory(self) -> Path:
        """Initialize the checks directory with sample checks."""
        self.checks_dir.mkdir(parents=True, exist_ok=True)

        # Create sample checks
        samples = {
            "security-review.md": self._security_check(),
            "code-quality.md": self._quality_check(),
            "documentation.md": self._docs_check(),
            "performance.md": self._performance_check(),
            "accessibility.md": self._accessibility_check(),
            "dependencies.md": self._dependencies_check(),
            "type-safety.md": self._type_safety_check(),
        }

        for filename, content in samples.items():
            path = self.checks_dir / filename
            if not path.exists():
                path.write_text(content)

        return self.checks_dir

    def _security_check(self) -> str:
        return """---
name: Security Review
description: Review code for common security issues
severity: error
files:
- "*.py"
- "*.js"
- "*.ts"
patterns:
        - "password\\s*="
        - "secret\\s*="
        - "token\\s*="
        - "api_key\\s*="
        - "eval\\s*\\("
        - "exec\\s*\\("
auto_fix: false
---
Review this code for security issues:
- No hardcoded secrets or credentials
- No dangerous eval/exec usage
- Proper input validation
- Safe error handling without information leakage
"""

    def _quality_check(self) -> str:
        return """---
name: Code Quality
description: Check code quality and best practices
severity: warning
files:
- "*.py"
- "*.js"
- "*.ts"
patterns:
- "TODO"
- "FIXME"
- "XXX"
auto_fix: false
---
Review this code for quality issues:
- No unresolved TODO/FIXME comments
- Proper error handling
- Clear variable and function names
- Reasonable function length
"""

    def _docs_check(self) -> str:
        return """---
name: Documentation
description: Check for missing documentation
severity: warning
files:
- "*.py"
patterns:
- "def __"
auto_fix: false
---
Review this code for documentation:
- Public functions have docstrings
- Complex logic has comments
- Module has a docstring
"""

    def _performance_check(self) -> str:
        return """---
name: Performance
description: Check for performance issues
severity: warning
files:
- "*.py"
- "*.js"
- "*.ts"
patterns:
- "time\\.sleep"
- "range\\(len"
- "\\.append\\("
- "for .* in range"
auto_fix: false
---
Review this code for performance issues:
- No busy-waiting or unnecessary sleeps
- Prefer enumerate() over range(len())
- Consider list comprehensions over loops
- Check for N+1 queries or repeated operations
"""

    def _accessibility_check(self) -> str:
        return """---
name: Accessibility
description: Check for accessibility issues
severity: warning
files:
- "*.html"
- "*.jsx"
- "*.tsx"
- "*.vue"
patterns:
- "<img[^>]*>(?!.*alt)"
- "onclick"
- "tabindex="
auto_fix: false
---
Review this code for accessibility issues:
- Images have alt text
- Interactive elements are keyboard accessible
- Proper heading hierarchy
- Sufficient color contrast
"""

    def _dependencies_check(self) -> str:
        return """---
name: Dependencies
description: Check for dependency issues
severity: warning
files:
- "requirements.txt"
- "package.json"
- "pyproject.toml"
- "Cargo.toml"
patterns:
- "=="
- "latest"
auto_fix: false
---
Review dependencies for issues:
- Pin versions explicitly (avoid 'latest')
- Check for known vulnerabilities
- Remove unused dependencies
- Keep dependencies up to date
"""

    def _type_safety_check(self) -> str:
        return """---
name: Type Safety
description: Check for type safety issues
severity: warning
files:
- "*.py"
- "*.ts"
patterns:
- "def .*\\([^)]*\\)(?!\\s*->)"
- "Any"
auto_fix: false
---
Review this code for type safety:
- Functions have return type annotations
- Avoid using 'Any' type
- Complex types use aliases
- Type hints are consistent
"""
