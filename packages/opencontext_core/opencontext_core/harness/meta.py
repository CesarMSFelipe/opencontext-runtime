"""MetaHarnessScanner — pre-flight capability readiness scanner.

Runs 11 independent checks and scores the installation 0-100.
Weight scheme: 9 checks x 10 points + 2 checks x 5 points = 100.
Gate: score >= 90 -> passed=True.

Each check is wrapped in try/except so a failure in one check never prevents
the remaining checks from running.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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


# 11 checks: 9 x 10 + 2 x 5 = 100
_WEIGHTS = [10, 10, 10, 10, 10, 10, 10, 10, 10, 5, 5]


class MetaHarnessScanner:
    """Runs all 11 pre-flight checks and produces a MetaHarnessReport."""

    def __init__(self, root: Path | str | None = None) -> None:
        self._root: Path = Path(root) if root is not None else Path.cwd()

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
            ("mcp_json", self._check_mcp_json),
            ("opencontext_yaml", self._check_opencontext_yaml),
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
        """Probe .claude/agents/.opencontext-delegates/ on disk in the project root.

        Requires at least 10 delegate files to pass (behavioral, not import-only).
        """
        try:
            delegates_dir = self._root / ".claude" / "agents" / ".opencontext-delegates"
            if not delegates_dir.exists():
                return False, (
                    f"Delegates directory not found: {delegates_dir!s} "
                    "(run 'opencontext install' to provision)"
                )
            entries = [e for e in delegates_dir.iterdir() if e.is_file()]
            if len(entries) >= 10:
                return True, f"{len(entries)} delegate file(s) in {delegates_dir!s}"
            return False, (
                f"Only {len(entries)} delegate file(s) found in {delegates_dir!s} "
                "(expected ≥ 10; run 'opencontext install' to provision)"
            )
        except Exception as exc:
            return False, f"Delegates path check failed: {exc}"

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

        cwd = self._root
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
                return True, f"KG populated: {count} node(s) in {db!s}"
            return False, "KG db exists but is empty — run 'opencontext index .' first"

        json_path = cwd / ".opencontext" / "knowledge_graph.json"
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                nodes = data.get("nodes") if isinstance(data, dict) else None
                if nodes:
                    return True, f"KG populated: {len(nodes)} node(s) in {json_path!s}"
                return False, "KG snapshot exists but has no nodes — run 'opencontext index .'"
            except Exception as exc:
                return False, f"KG snapshot present but unreadable: {exc}"

        return (
            False,
            "No KG artifact found (expected .storage/opencontext/context_graph.db "
            "or .opencontext/knowledge_graph.json) — run 'opencontext index .' first",
        )

    def _check_context_substrate(self) -> tuple[bool, str]:
        """Call build_for_phase against self._root and assert context_pack_hash is not None.

        D2: the check must exercise the real SQLite read path (not just report
        available_tokens on an empty dir which was a false-green before this fix).
        If self._root has no populated KG, the hash will be None → failed.
        """
        try:
            from opencontext_core.agentic.context_substrate import ContextSubstrateBuilder

            builder = ContextSubstrateBuilder(root=self._root)
            report = builder.build_for_phase(
                task="meta-harness-check", phase="explore", budget=4000
            )
            if report.context_pack_hash is None:
                reason = "; ".join(report.warnings) if report.warnings else "hash is None"
                return False, f"Context substrate degraded: {reason}"
            if report.used_tokens <= 0:
                return False, "Context substrate degraded: used_tokens <= 0"
            if report.selected_tokens <= 0:
                return False, "Context substrate degraded: selected_tokens <= 0"
            if report.baseline_tokens < report.selected_tokens:
                return False, "Context substrate degraded: baseline_tokens < selected_tokens"
            if report.warnings:
                return False, f"Context substrate warnings: {'; '.join(report.warnings)}"
            return (
                True,
                f"substrate ok: hash={report.context_pack_hash}, tokens={report.used_tokens}",
            )
        except Exception as exc:
            return False, f"Context substrate build failed: {exc}"

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
        """Verify OcNewArchiveGate (the correct archive gate class) is importable."""
        try:
            from opencontext_core.oc_new.archive_gate import OcNewArchiveGate  # noqa: F401

            return True, "OcNewArchiveGate importable (correct archive gate class)"
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
            import importlib

            mod = importlib.import_module("opencontext_cli.commands.uninstall_cmd")
            if not hasattr(mod, "handle_uninstall"):
                return False, "handle_uninstall not found in uninstall_cmd"
            return True, "uninstall_cmd importable"
        except Exception as exc:
            return False, f"Import failed: {exc}"

    def _check_mcp_json(self) -> tuple[bool, str]:
        """Check that .mcp.json is present in the project root."""
        mcp_path = self._root / ".mcp.json"
        if mcp_path.exists():
            return True, f".mcp.json present at {mcp_path!s}"
        return (
            False,
            f".mcp.json not found at {mcp_path!s} (run 'opencontext install' to provision)",
        )

    def _check_opencontext_yaml(self) -> tuple[bool, str]:
        """Check that opencontext.yaml is present in the project root."""
        yaml_path = self._root / "opencontext.yaml"
        if yaml_path.exists():
            return True, f"opencontext.yaml present at {yaml_path!s}"
        return (
            False,
            f"opencontext.yaml not found at {yaml_path!s} (run 'opencontext init' to create)",
        )
