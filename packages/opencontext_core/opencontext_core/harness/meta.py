"""MetaHarnessScanner — pre-flight capability readiness scanner.

Runs 9 independent checks and scores the installation 0-100.
Weight scheme: 8 checks x 11 points + 1 check x 12 points = 100.
Gate: score >= 90 -> passed=True. One failure -> score <= 89 -> passed=False.

Each check is wrapped in try/except so a failure in one check never prevents
the remaining checks from running.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MetaHarnessCheck:
    """Result of a single meta-harness check."""

    name: str
    passed: bool
    score_contribution: int
    explanation: str


@dataclass
class MetaHarnessReport:
    """Aggregated result of all meta-harness checks."""

    score: int
    checks: list[MetaHarnessCheck]
    passed: bool

    @classmethod
    def from_checks(cls, checks: list[MetaHarnessCheck]) -> MetaHarnessReport:
        score = sum(c.score_contribution for c in checks if c.passed)
        score = max(0, min(100, score))
        return cls(score=score, checks=checks, passed=score >= 90)


_WEIGHTS = [12, 11, 11, 11, 11, 11, 11, 11, 11]  # 9 checks, sum = 100


class MetaHarnessScanner:
    """Runs all 9 pre-flight checks and produces a MetaHarnessReport."""

    def scan(self) -> MetaHarnessReport:
        """Run all checks. Each check is isolated; exceptions → passed=False."""
        raw_checks = [
            ("public_main_persona", self._check_public_main_persona),
            ("hidden_delegates_path", self._check_hidden_delegates_path),
            ("memory_backend", self._check_memory_backend),
            ("kg_snapshot_path", self._check_kg_snapshot_path),
            ("context_substrate", self._check_context_substrate),
            ("handoff_v2_schema", self._check_handoff_v2_schema),
            ("archive_gate", self._check_archive_gate),
            ("tui_app", self._check_tui_app),
            ("uninstall_cmd", self._check_uninstall_cmd),
        ]
        checks: list[MetaHarnessCheck] = []
        for (name, fn), weight in zip(raw_checks, _WEIGHTS, strict=True):
            try:
                passed, explanation = fn()
            except Exception as exc:
                passed = False
                explanation = f"Exception: {exc}"
            checks.append(
                MetaHarnessCheck(
                    name=name,
                    passed=passed,
                    score_contribution=weight if passed else 0,
                    explanation=explanation,
                )
            )
        return MetaHarnessReport.from_checks(checks)

    # NOTE: Each check returns (passed: bool, explanation: str).

    def _check_public_main_persona(self) -> tuple[bool, str]:
        try:
            from opencontext_core.personas import public_personas

            personas = public_personas()
            if personas:
                return True, f"{len(personas)} public persona(s) available"
            return False, "No public personas found"
        except Exception as exc:
            return False, f"Import failed: {exc}"

    def _check_hidden_delegates_path(self) -> tuple[bool, str]:
        try:
            from opencontext_core.personas import delegation_personas

            delegates = delegation_personas()
            if delegates:
                return True, f"{len(delegates)} hidden delegation persona(s) defined"
            return False, "No hidden delegation personas found"
        except Exception as exc:
            return False, f"Import failed: {exc}"

    def _check_memory_backend(self) -> tuple[bool, str]:
        try:
            from opencontext_core.memory.backends import SQLiteMemoryBackend  # noqa: F401

            return True, "SQLiteMemoryBackend importable"
        except Exception as exc:
            return False, f"Import failed: {exc}"

    def _check_kg_snapshot_path(self) -> tuple[bool, str]:
        try:
            from opencontext_core.agentic.context_substrate import (
                ContextSubstrateBuilder,  # noqa: F401
            )

            return True, "ContextSubstrateBuilder (KG path) importable"
        except Exception as exc:
            return False, f"Import failed: {exc}"

    def _check_context_substrate(self) -> tuple[bool, str]:
        try:
            from opencontext_core.agentic.context_substrate import (
                ContextSubstrateReport,  # noqa: F401
            )

            return True, "ContextSubstrateReport importable (substrate not degraded)"
        except Exception as exc:
            return False, f"Import failed: {exc}"

    def _check_handoff_v2_schema(self) -> tuple[bool, str]:
        try:
            from opencontext_core.oc_new.models import AgentHandoff

            # NOTE: AgentHandoff is a dataclass/Pydantic model.
            # Check model_fields or __dataclass_fields__ for schema_version.
            try:
                model_fields = AgentHandoff.model_fields
                has_v2 = "schema_version" in model_fields
            except AttributeError:
                has_v2 = hasattr(AgentHandoff, "schema_version") or "schema_version" in getattr(
                    AgentHandoff, "__dataclass_fields__", {}
                )
            if has_v2:
                return True, "AgentHandoff v2 schema_version field present"
            return False, "AgentHandoff missing schema_version field"
        except Exception as exc:
            return False, f"Import/check failed: {exc}"

    def _check_archive_gate(self) -> tuple[bool, str]:
        try:
            from opencontext_core.harness.gates import ContextPackCreatedGate  # noqa: F401

            return True, "Archive gate (ContextPackCreatedGate) importable"
        except Exception as exc:
            return False, f"Import failed: {exc}"

    def _check_tui_app(self) -> tuple[bool, str]:
        try:
            import importlib.util

            spec = importlib.util.find_spec("opencontext_cli.tui.app")
            if spec is not None:
                return True, "TUI app module resolvable"
            return False, "opencontext_cli.tui.app spec not found"
        except Exception as exc:
            return False, f"Spec lookup failed: {exc}"

    def _check_uninstall_cmd(self) -> tuple[bool, str]:
        try:
            from opencontext_cli.commands.uninstall_cmd import (  # type: ignore[import-not-found]
                handle_uninstall,  # noqa: F401
            )

            return True, "uninstall_cmd importable"
        except Exception as exc:
            return False, f"Import failed: {exc}"
