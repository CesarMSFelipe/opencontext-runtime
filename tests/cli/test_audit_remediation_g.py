"""Regression tests for audit-remediation-2026-07 Slice G findings.

Findings covered:
  CRIT-1 — opencontext_sdd missing from build_binary._PACKAGES + top-level import
  WARN-1  — tests_pass gate not declared in any builtin YAML
  WARN-2  — mypy [unused-ignore] on main.py:2563 sys.stdout assignment
  SUGG-1  — stale comment in sdd_cmd.py:120

TDD cycle: these tests are written BEFORE the fixes (RED), then made GREEN.
"""

from __future__ import annotations

import importlib
import sys
import textwrap
import types
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# CRIT-1 (a) — opencontext_sdd must be in build_binary._PACKAGES
# ---------------------------------------------------------------------------


class TestBuildBinaryPackages:
    """CRIT-1a: build_binary._PACKAGES must bundle opencontext_sdd."""

    def test_opencontext_sdd_in_packages(self) -> None:
        """opencontext_sdd must be listed in _PACKAGES so the pyz is self-contained."""
        import scripts.build_binary as bb
        assert "opencontext_sdd" in bb._PACKAGES, (
            "opencontext_sdd is missing from scripts/build_binary.py _PACKAGES. "
            "The pyz will crash with ModuleNotFoundError on a clean machine."
        )

    def test_opencontext_sdd_source_path_exists(self) -> None:
        """The source path recorded for opencontext_sdd must actually exist."""
        import scripts.build_binary as bb
        if "opencontext_sdd" not in bb._PACKAGES:
            pytest.skip("opencontext_sdd not in _PACKAGES yet (CRIT-1a fix pending)")
        src = bb._PACKAGES["opencontext_sdd"]
        assert src.is_dir(), f"opencontext_sdd source not found at {src}"


# ---------------------------------------------------------------------------
# CRIT-1 (b) — sdd_cmd must be importable without opencontext_sdd installed
# ---------------------------------------------------------------------------


class TestSddCmdLazyImport:
    """CRIT-1b: sdd_cmd must not fail at CLI startup when opencontext_sdd is absent."""

    def test_sdd_cmd_importable_without_opencontext_sdd(self) -> None:
        """Importing sdd_cmd must succeed even if opencontext_sdd is not available.

        A top-level 'from opencontext_sdd.runner import ...' breaks every unrelated
        CLI command (e.g. 'opencontext version') on a clean machine where sdd is not
        installed. The import must be lazy (inside the functions that use it).
        """
        # Remove cached module so we get a fresh import
        mods_to_evict = [k for k in sys.modules if "sdd_cmd" in k]
        for m in mods_to_evict:
            del sys.modules[m]

        # Block opencontext_sdd entirely — simulates clean machine
        fake_blocker = types.ModuleType("opencontext_sdd")
        fake_runner = types.ModuleType("opencontext_sdd.runner")

        def _raise(*a: object, **kw: object) -> None:
            raise ImportError("opencontext_sdd not installed")

        fake_blocker.__getattr__ = _raise  # type: ignore[attr-defined]
        fake_runner.__getattr__ = _raise  # type: ignore[attr-defined]

        with patch.dict(
            sys.modules,
            {"opencontext_sdd": fake_blocker, "opencontext_sdd.runner": fake_runner},
        ):
            # Fresh import — must NOT raise at module level
            try:
                spec = importlib.util.find_spec(  # type: ignore[attr-defined]
                    "opencontext_cli.commands.sdd_cmd"
                )
                if spec is None:
                    pytest.skip("sdd_cmd not on path in this env")
                loader = importlib.util.module_from_spec(spec)  # type: ignore[attr-defined]
                # Module-level execution must not ImportError
                spec.loader.exec_module(loader)  # type: ignore[union-attr]
            except ImportError as exc:
                pytest.fail(
                    f"sdd_cmd raised ImportError at module level when "
                    f"opencontext_sdd is missing: {exc}. "
                    "Move the 'from opencontext_sdd.runner import ...' inside the "
                    "functions that use it."
                )

    def test_no_toplevel_opencontext_sdd_import_in_sdd_cmd_source(self) -> None:
        """sdd_cmd.py must not have an unconditional top-level opencontext_sdd import.

        A 'from opencontext_sdd ...' inside 'if TYPE_CHECKING:' is acceptable — it
        never executes at runtime.  An unconditional top-level import crashes every
        CLI command on a clean machine where sdd is absent.
        """
        sdd_cmd_path = (
            ROOT
            / "packages"
            / "opencontext_cli"
            / "opencontext_cli"
            / "commands"
            / "sdd_cmd.py"
        )
        source = sdd_cmd_path.read_text(encoding="utf-8")
        lines = source.splitlines()
        in_type_checking_block = False
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            # Stop scanning at the first function/class definition — anything
            # before those is module-level code.
            if stripped.startswith("def ") or stripped.startswith("class "):
                break
            # Track entry into TYPE_CHECKING guard — imports inside are
            # type-only and never executed at runtime.
            if stripped == "if TYPE_CHECKING:":
                in_type_checking_block = True
                continue
            # Exit TYPE_CHECKING block when indentation returns to 0
            if in_type_checking_block and line and not line[0].isspace():
                in_type_checking_block = False
            if in_type_checking_block:
                continue
            if stripped.startswith("from opencontext_sdd") or stripped.startswith(
                "import opencontext_sdd"
            ):
                pytest.fail(
                    f"sdd_cmd.py line {i} has an unconditional top-level opencontext_sdd "
                    f"import: {line!r}. This crashes CLI startup when the package is absent. "
                    "Move the import inside a function body or guard it with TYPE_CHECKING."
                )


# ---------------------------------------------------------------------------
# WARN-1 — tests_pass gate must be declared in inspection.yaml
# ---------------------------------------------------------------------------


class TestTestsPassGateInBuiltinYaml:
    """WARN-1: tests_pass must appear in inspection.yaml so it activates in strict mode."""

    def _load_inspection_yaml(self) -> dict:  # type: ignore[type-arg]
        path = (
            ROOT
            / "packages"
            / "opencontext_core"
            / "opencontext_core"
            / "harness"
            / "builtins"
            / "inspection.yaml"
        )
        with path.open() as f:
            return yaml.safe_load(f)

    def test_tests_pass_declared_in_inspection_yaml(self) -> None:
        """tests_pass gate must be in inspection.yaml gates list."""
        data = self._load_inspection_yaml()
        gates: list[str] = data.get("gates", [])
        assert "tests_pass" in gates, (
            "tests_pass is not declared in inspection.yaml gates. "
            "TestsPassGate is wired in _dispatch_one_gate but never reached because "
            "no builtin phase YAML declares it. Add 'tests_pass' to inspection.yaml."
        )

    def test_tests_pass_gate_no_ops_in_non_strict_mode(self) -> None:
        """tests_pass gate returns PASSED immediately when tdd_mode != strict.

        This confirms that adding tests_pass to the YAML is safe for non-strict
        projects — the gate never executes a subprocess unless tdd_mode='strict'.
        """
        from opencontext_core.harness.gates import TestsPassGate
        from opencontext_core.harness.models import GateStatus

        gate = TestsPassGate()
        result = gate.evaluate(cmd=["pytest"], cwd=ROOT, tdd_mode="ask")
        assert result.status == GateStatus.PASSED
        assert "inactive" in result.message.lower()

    def test_tests_pass_gate_activates_in_strict_mode_on_failure(
        self, tmp_path: Path
    ) -> None:
        """tests_pass gate returns FAILED in strict mode when tests fail."""
        from opencontext_core.harness.gates import TestsPassGate
        from opencontext_core.harness.models import GateStatus

        # Write a minimal failing test file
        test_file = tmp_path / "test_failing.py"
        test_file.write_text(
            textwrap.dedent("""\
                def test_always_fails():
                    assert False, 'intentional RED'
            """),
            encoding="utf-8",
        )

        gate = TestsPassGate()
        result = gate.evaluate(
            cmd=["python", "-m", "pytest", str(test_file), "-q", "--tb=no"],
            cwd=tmp_path,
            tdd_mode="strict",
        )
        assert result.status == GateStatus.FAILED, (
            f"Expected FAILED, got {result.status}: {result.message}"
        )


# ---------------------------------------------------------------------------
# WARN-2 — mypy must not report [unused-ignore] for main.py:2563
# ---------------------------------------------------------------------------


class TestMypyNoUnusedIgnoreInMainPy:
    """WARN-2: mypy must be clean for opencontext_cli.main (no [unused-ignore])."""

    def test_no_unused_ignore_annotation_on_stdout_assignment(self) -> None:
        """main.py sys.stdout assignment type-ignore must not be flagged as unused.

        The fix is a [[tool.mypy.overrides]] entry with warn_unused_ignores=false
        for opencontext_cli.main in pyproject.toml.
        """
        pyproject = ROOT / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8")

        # The override must target opencontext_cli.main specifically.
        assert "opencontext_cli.main" in content, (
            "pyproject.toml has no mypy override for opencontext_cli.main. "
            "Add [[tool.mypy.overrides]] with module='opencontext_cli.main' "
            "and warn_unused_ignores=false."
        )

    def test_pyproject_main_override_sets_warn_unused_ignores_false(self) -> None:
        """The opencontext_cli.main override must set warn_unused_ignores = false."""
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]

        pyproject = ROOT / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

        overrides: list[dict] = (  # type: ignore[assignment]
            data.get("tool", {}).get("mypy", {}).get("overrides", [])
        )
        main_override = next(
            (
                o
                for o in overrides
                if o.get("module") == "opencontext_cli.main"
            ),
            None,
        )
        assert main_override is not None, (
            "No [[tool.mypy.overrides]] entry found with module='opencontext_cli.main'."
        )
        assert main_override.get("warn_unused_ignores") is False, (
            f"opencontext_cli.main override does not set warn_unused_ignores=false. "
            f"Got: {main_override}"
        )


# ---------------------------------------------------------------------------
# SUGG-1 — stale comment in sdd_cmd.py must be updated
# ---------------------------------------------------------------------------


class TestSddCmdStaleComment:
    """SUGG-1: stale stub comment at line 120 must be removed/updated."""

    def test_no_stub_comment_in_sdd_cmd(self) -> None:
        """sdd_cmd.py must not contain the stale 'stub until PR4.a ships' comment."""
        sdd_cmd_path = (
            ROOT
            / "packages"
            / "opencontext_cli"
            / "opencontext_cli"
            / "commands"
            / "sdd_cmd.py"
        )
        source = sdd_cmd_path.read_text(encoding="utf-8")
        assert "stub until PR4.a ships" not in source, (
            "Stale comment 'stub until PR4.a ships runner.py' still present in "
            "sdd_cmd.py. The function is live — update or remove the comment."
        )
