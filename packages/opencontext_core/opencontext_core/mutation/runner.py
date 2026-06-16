"""MutationRunner — framework-agnostic mutation analysis."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from opencontext_core.mutation.models import MutationResult

# Internal framework identifiers (never exposed in output)
_FRAMEWORK_PYTHON_A = "mutmut"
_FRAMEWORK_PYTHON_B = "cosmic-ray"
_FRAMEWORK_PHP = "infection"
_FRAMEWORK_RUST = "cargo-mutants"


class MutationRunner:
    """Run mutation analysis using whichever framework is installed.

    Framework detection is private. Output uses only OpenContext-native
    terminology: "mutation analysis", "mutation coverage", "mutants killed".
    """

    def run(
        self,
        root: Path,
        scope: str = "changed",
        threshold: int = 80,
    ) -> MutationResult:
        """Run mutation analysis and return a framework-neutral MutationResult.

        Args:
            root: Project root directory.
            scope: Scope of analysis ("changed" or "all").
            threshold: Minimum passing mutation coverage score (0-100).

        Returns:
            MutationResult with score/killed/survivors/available fields.
        """
        framework = self._detect_framework(root)
        if framework is None:
            return MutationResult(
                score=0.0,
                killed=0,
                survivors=0,
                available=False,
                framework="none",
                error="Mutation analysis framework not found in this environment.",
            )

        try:
            return self._run_framework(root, framework, scope)
        except Exception as exc:
            return MutationResult(
                score=0.0,
                killed=0,
                survivors=0,
                available=False,
                framework=framework,
                error=f"Mutation analysis failed: {exc}",
            )

    def _detect_framework(self, root: Path) -> str | None:
        """Private: detect which mutation framework is available."""
        # Python frameworks
        if shutil.which(_FRAMEWORK_PYTHON_A):
            return _FRAMEWORK_PYTHON_A
        if shutil.which(_FRAMEWORK_PYTHON_B):
            return _FRAMEWORK_PYTHON_B
        # PHP framework (check vendor/bin/)
        php_bin = root / "vendor" / "bin" / _FRAMEWORK_PHP
        if php_bin.exists():
            return _FRAMEWORK_PHP
        # Rust framework (check Cargo.toml + cargo subcommand)
        if (root / "Cargo.toml").exists() and self._cargo_subcommand_available("mutants"):
            return _FRAMEWORK_RUST
        return None

    @staticmethod
    def _cargo_subcommand_available(subcommand: str) -> bool:
        """Check whether a cargo subcommand is available."""
        try:
            result = subprocess.run(
                ["cargo", subcommand, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _run_framework(self, root: Path, framework: str, scope: str) -> MutationResult:
        """Run the detected framework and parse results generically."""
        if framework == _FRAMEWORK_PYTHON_A:
            return self._run_mutmut(root, scope)
        if framework == _FRAMEWORK_PYTHON_B:
            return self._run_cosmic_ray(root, scope)
        if framework == _FRAMEWORK_PHP:
            return self._run_infection(root, scope)
        if framework == _FRAMEWORK_RUST:
            return self._run_cargo_mutants(root, scope)
        return MutationResult(
            score=0.0,
            killed=0,
            survivors=0,
            available=False,
            framework=framework,
            error="Mutation analysis framework not supported.",
        )

    def _run_mutmut(self, root: Path, scope: str) -> MutationResult:
        """Run Python mutation framework A and parse results."""
        cmd = [_FRAMEWORK_PYTHON_A, "run", "--no-progress"]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=root)
        except Exception:
            pass
        # Parse results
        try:
            result = subprocess.run(
                [_FRAMEWORK_PYTHON_A, "results"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=root,
            )
            return self._parse_generic_output(result.stdout + result.stderr, _FRAMEWORK_PYTHON_A)
        except Exception as exc:
            return MutationResult(
                score=0.0,
                killed=0,
                survivors=0,
                available=False,
                framework=_FRAMEWORK_PYTHON_A,
                error=f"Mutation analysis output unavailable: {exc}",
            )

    def _run_cosmic_ray(self, root: Path, scope: str) -> MutationResult:
        """Run Python mutation framework B."""
        try:
            result = subprocess.run(
                [_FRAMEWORK_PYTHON_B, "run", "cosmic_ray_config.toml"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=root,
            )
            return self._parse_generic_output(result.stdout + result.stderr, _FRAMEWORK_PYTHON_B)
        except Exception as exc:
            return MutationResult(
                score=0.0,
                killed=0,
                survivors=0,
                available=False,
                framework=_FRAMEWORK_PYTHON_B,
                error=f"Mutation analysis output unavailable: {exc}",
            )

    def _run_infection(self, root: Path, scope: str) -> MutationResult:
        """Run PHP mutation framework."""
        bin_path = root / "vendor" / "bin" / _FRAMEWORK_PHP
        try:
            result = subprocess.run(
                [str(bin_path), "--no-progress", "--formatter=json"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=root,
            )
            return self._parse_generic_output(result.stdout + result.stderr, _FRAMEWORK_PHP)
        except Exception as exc:
            return MutationResult(
                score=0.0,
                killed=0,
                survivors=0,
                available=False,
                framework=_FRAMEWORK_PHP,
                error=f"Mutation analysis output unavailable: {exc}",
            )

    def _run_cargo_mutants(self, root: Path, scope: str) -> MutationResult:
        """Run Rust mutation framework."""
        try:
            result = subprocess.run(
                ["cargo", "mutants", "--no-shuffle"],
                capture_output=True,
                text=True,
                timeout=600,
                cwd=root,
            )
            return self._parse_generic_output(result.stdout + result.stderr, _FRAMEWORK_RUST)
        except Exception as exc:
            return MutationResult(
                score=0.0,
                killed=0,
                survivors=0,
                available=False,
                framework=_FRAMEWORK_RUST,
                error=f"Mutation analysis output unavailable: {exc}",
            )

    @staticmethod
    def _parse_generic_output(output: str, framework: str) -> MutationResult:
        """Parse framework output generically into score/killed/survivors.

        Looks for common patterns like "killed: N", "survived: N",
        "score: N%", etc., regardless of framework.
        """
        killed = 0
        survivors = 0

        # Pattern: "N killed" or "killed: N" or "Killed: N"
        for pat in (r"(\d+)\s+killed", r"killed[:\s]+(\d+)"):
            m = re.search(pat, output, re.IGNORECASE)
            if m:
                killed = int(m.group(1))
                break

        # Pattern: "N survived" / "survived: N" / "N survivors"
        for pat in (r"(\d+)\s+survived", r"survived[:\s]+(\d+)", r"(\d+)\s+survivors"):
            m = re.search(pat, output, re.IGNORECASE)
            if m:
                survivors = int(m.group(1))
                break

        total = killed + survivors
        if total > 0:
            score = (killed / total) * 100.0
        else:
            # Check for explicit score in output
            score_match = re.search(r"(\d+(?:\.\d+)?)\s*%", output)
            score = float(score_match.group(1)) if score_match else 0.0

        # Clamp to [0.0, 100.0]
        score = max(0.0, min(100.0, score))

        return MutationResult(
            score=score,
            killed=killed,
            survivors=survivors,
            available=True,
            framework=framework,
        )
