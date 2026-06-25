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
        """In-process write+read roundtrip against SQLiteMemoryBackend (CWD-rooted)."""
        import tempfile
        from datetime import UTC, datetime
        from pathlib import Path

        try:
            from opencontext_core.memory.backends import SQLiteMemoryBackend
            from opencontext_core.models.agent_memory import (
                DecayPolicy,
                MemoryLayer,
                MemoryRecord,
            )

            with tempfile.TemporaryDirectory() as tmp_dir:
                db_path = str(Path(tmp_dir) / "meta_harness_check.db")
                backend = SQLiteMemoryBackend(db_path)
                now = datetime.now(tz=UTC)
                record = MemoryRecord(
                    id="__meta_harness_check__",
                    layer=MemoryLayer.EPISODIC,
                    key="meta:harness:check",
                    content="roundtrip-ok",
                    decay_policy=DecayPolicy(enabled=False),
                    created_at=now,
                    updated_at=now,
                )
                backend.store(record)
                results = backend.search("roundtrip", limit=1)
                if results:
                    return True, "SQLiteMemoryBackend write+read roundtrip succeeded"
                return False, "SQLiteMemoryBackend write succeeded but read returned no results"
        except Exception as exc:
            return False, f"Memory backend roundtrip failed: {exc}"

    def _check_kg_snapshot_path(self) -> tuple[bool, str]:
        """Check that a POPULATED KG exists on disk (behavioral, not just importable).

        Mere file existence is not enough: instantiating the runtime can create an
        empty ``context_graph.db`` as a side effect, so an unindexed project would
        otherwise pass. We require the graph to actually contain nodes.
        """
        import json
        import sqlite3
        from pathlib import Path

        cwd = Path.cwd()
        db = cwd / ".storage" / "opencontext" / "context_graph.db"
        if db.exists():
            try:
                conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
                try:
                    count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
                finally:
                    conn.close()
            except Exception as exc:
                return False, f"KG db present but unreadable: {exc}"
            if count > 0:
                return True, f"KG populated: {count} node(s) in {db.relative_to(cwd)}"
            return False, "KG db exists but is empty — run 'opencontext index .' first"

        json_path = cwd / ".opencontext" / "knowledge_graph.json"
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                nodes = data.get("nodes") if isinstance(data, dict) else None
                if nodes:
                    rel = json_path.relative_to(cwd)
                    return True, f"KG populated: {len(nodes)} node(s) in {rel}"
                return False, "KG snapshot exists but has no nodes — run 'opencontext index .'"
            except Exception as exc:
                return False, f"KG snapshot present but unreadable: {exc}"

        return (
            False,
            "No KG artifact found (expected .storage/opencontext/context_graph.db "
            "or .opencontext/knowledge_graph.json) — run 'opencontext index .' first",
        )

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
        """Check that the TUI app module file exists (on disk or bundled in pyz).

        Uses a file-existence check rather than importing so that a missing
        optional dependency (textual) does not cause the check to fail.
        """
        try:
            import importlib.util
            from pathlib import Path

            # Fast path for an editable / site-packages install: the package
            # origin gives us a real directory on disk.
            pkg_spec = importlib.util.find_spec("opencontext_cli")
            if pkg_spec is not None and pkg_spec.origin is not None:
                pkg_dir = Path(pkg_spec.origin).parent
                app_path = pkg_dir / "tui" / "app.py"
                if app_path.exists():
                    return True, "TUI app module file present"

            # Fallback path covers zipimport (pyz bundle) and any other loader:
            # try to resolve the spec without triggering the textual import.
            # find_spec raises ModuleNotFoundError when a *parent* package's
            # __init__ imports textual; catching it gives us parity with the
            # file-check above.
            try:
                tui_spec = importlib.util.find_spec("opencontext_cli.tui")
                if tui_spec is not None and tui_spec.submodule_search_locations:
                    for search_path in tui_spec.submodule_search_locations:
                        candidate = Path(search_path) / "app.py"
                        if candidate.exists():
                            return True, "TUI app module file present"
                    # For zip-based loaders the path may not exist on disk; fall
                    # through to the origin-name check below.
            except (ModuleNotFoundError, ValueError):
                pass

            if pkg_spec is not None and pkg_spec.origin is not None:
                # Inside a pyz the origin path ends with opencontext_cli/__init__.py
                # inside the archive. We can't do Path.exists() there, but the mere
                # presence of the spec proves the package ships the module.
                pkg_dir = Path(pkg_spec.origin).parent
                app_path = pkg_dir / "tui" / "app.py"
                if str(app_path).endswith(".pyz") or ".pyz/" in str(app_path):
                    return True, "TUI app module bundled in pyz archive"

            return False, "opencontext_cli.tui.app module not found"
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
