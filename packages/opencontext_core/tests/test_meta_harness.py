"""Tests for D6: MetaHarnessScanner, report scoring, and independence."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.meta import MetaHarnessCheck, MetaHarnessReport, MetaHarnessScanner


class TestMetaHarnessReport:
    def test_all_pass_score_100(self) -> None:
        # 9 x 10 + 2 x 5 = 100
        weights = [10, 10, 10, 10, 10, 10, 10, 10, 10, 5, 5]
        checks = [
            MetaHarnessCheck(name=f"check_{i}", passed=True, score_contribution=w, explanation="OK")
            for i, w in enumerate(weights)
        ]
        report = MetaHarnessReport.from_checks(checks)
        assert report.score == 100
        assert report.passed is True

    def test_multiple_fails_drop_below_90(self) -> None:
        # 9 pass x 10 + 2 fail x 5 (5-weight checks) = 90 → still passes (boundary)
        # 9 pass x 10 + 1 pass x 5 + 1 fail x 5 = 95 → passes (only one 5-weight fails)
        # 2 fail x 10 + 9 pass x 10 = 90 → boundary (still passes)
        # 3 fail x 10 + 8 pass x 10 = 80 → fails
        # Verify that enough failures drive the score below gate.
        checks = [
            MetaHarnessCheck(
                name=f"fail_{i}", passed=False, score_contribution=0, explanation="fail"
            )
            for i in range(3)  # 3 failures x 10 = 30 lost -> 100 - 30 = 70 < 90
        ]
        checks += [
            MetaHarnessCheck(
                name=f"check_{i}", passed=True, score_contribution=10, explanation="OK"
            )
            for i in range(8)
        ]
        report = MetaHarnessReport.from_checks(checks)
        assert report.score <= 89
        assert report.passed is False

    def test_score_gate_at_90(self) -> None:
        # Exactly 90 → passed
        checks_90 = [
            MetaHarnessCheck(name=f"c{i}", passed=True, score_contribution=10, explanation="OK")
            for i in range(9)
        ]
        report_90 = MetaHarnessReport.from_checks(checks_90)
        assert report_90.score == 90
        assert report_90.passed is True

        # 89 → not passed
        checks_89 = [
            *checks_90[:-1],
            MetaHarnessCheck(name="c8", passed=True, score_contribution=9, explanation="OK"),
        ]
        report_89 = MetaHarnessReport.from_checks(checks_89)
        assert report_89.score == 89
        assert report_89.passed is False

    def test_score_clamped_0_100(self) -> None:
        checks_over = [
            MetaHarnessCheck(name=f"c{i}", passed=True, score_contribution=20, explanation="OK")
            for i in range(9)
        ]
        report = MetaHarnessReport.from_checks(checks_over)
        assert report.score <= 100

        checks_zero = [
            MetaHarnessCheck(name=f"c{i}", passed=False, score_contribution=0, explanation="fail")
            for i in range(9)
        ]
        report_z = MetaHarnessReport.from_checks(checks_zero)
        assert report_z.score >= 0


class TestMetaHarnessScanner:
    def test_scan_returns_11_checks(self) -> None:
        scanner = MetaHarnessScanner()
        report = scanner.scan()
        assert len(report.checks) == 11

    def test_check_names_are_unique(self) -> None:
        scanner = MetaHarnessScanner()
        report = scanner.scan()
        names = [c.name for c in report.checks]
        assert len(names) == len(set(names))

    def test_expected_check_names_present(self) -> None:
        scanner = MetaHarnessScanner()
        report = scanner.scan()
        names = {c.name for c in report.checks}
        expected = {
            "public_main_persona",
            "hidden_delegates_path",
            "memory_backend",
            "kg_snapshot_path",
            "context_substrate",
            "handoff_v2_schema",
            "archive_gate",
            "tui_app",
            "uninstall_cmd",
            "mcp_json",
            "opencontext_yaml",
        }
        assert names == expected

    def test_exception_in_one_check_does_not_stop_others(self) -> None:
        """Monkey-patch one check to raise; all 11 checks must still run."""
        scanner = MetaHarnessScanner()
        original = scanner._check_memory_backend

        def _raises() -> tuple[bool, str]:
            raise RuntimeError("simulated check failure")

        scanner._check_memory_backend = _raises  # type: ignore[method-assign]
        report = scanner.scan()
        assert len(report.checks) == 11
        failing = next(c for c in report.checks if c.name == "memory_backend")
        assert failing.passed is False
        assert "simulated check failure" in failing.explanation

        scanner._check_memory_backend = original  # type: ignore[method-assign]

    def test_weights_sum_to_100(self) -> None:
        from opencontext_core.harness.meta import _WEIGHTS

        assert sum(_WEIGHTS) == 100
        assert len(_WEIGHTS) == 11


class TestKgSubstrateCheckIsBehavioral:
    """_check_context_substrate must exercise the real SQLite read path and verify
    context_pack_hash is not None — not just check available_tokens in an empty tempdir."""

    @staticmethod
    def _provision_real_schema_db(root: Path) -> None:
        """Create context_graph.db with the real NOT NULL schema + ≥1 row."""
        import sqlite3

        db_dir = root / ".storage" / "opencontext"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / "context_graph.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE nodes ("
            "id TEXT PRIMARY KEY NOT NULL, "
            "name TEXT NOT NULL, "
            "kind TEXT NOT NULL, "
            "file_path TEXT NOT NULL, "
            "language TEXT NOT NULL, "
            "content_snippet TEXT"
            ")"
        )
        conn.execute(
            "INSERT INTO nodes (id, name, kind, file_path, language, content_snippet) "
            "VALUES ('n1', 'n1', 'file', 'foo.py', 'python', 'hello world')"
        )
        conn.commit()
        conn.close()

    def test_substrate_check_passes_with_real_schema_db(self, tmp_path: Path) -> None:
        """_check_context_substrate must pass and report non-null hash when DB is populated."""
        self._provision_real_schema_db(tmp_path)
        scanner = MetaHarnessScanner(root=tmp_path)
        passed, explanation = scanner._check_context_substrate()
        assert passed is True, f"Expected passed=True, got explanation: {explanation}"
        assert "hash" in explanation or "tokens" in explanation, (
            f"Explanation must mention hash or tokens: {explanation}"
        )

    def test_substrate_check_fails_when_metrics_are_incomplete(
        self, tmp_path: Path, monkeypatch: object
    ) -> None:
        from opencontext_core.agentic.context_substrate import ContextSubstrateReport

        class BadBuilder:
            def __init__(self, root: Path) -> None:
                pass

            def build_for_phase(self, **kwargs: object) -> ContextSubstrateReport:
                return ContextSubstrateReport(
                    indexed=True,
                    graph_status="indexed",
                    context_pack_hash="sha256:x",
                    used_tokens=14,
                    selected_tokens=0,
                    baseline_tokens=0,
                    compressed_tokens=0,
                )

        monkeypatch.setattr(
            "opencontext_core.agentic.context_substrate.ContextSubstrateBuilder",
            BadBuilder,
        )
        passed, explanation = MetaHarnessScanner(root=tmp_path)._check_context_substrate()
        assert passed is False
        assert "selected_tokens" in explanation

    def test_substrate_check_fails_on_empty_dir(self, tmp_path: Path) -> None:
        """_check_context_substrate must return passed=False when no DB is provisioned."""
        # No DB provisioned — empty tmpdir.
        scanner = MetaHarnessScanner(root=tmp_path)
        passed, _explanation = scanner._check_context_substrate()
        assert passed is False, (
            "Empty tmpdir should return passed=False — check was false-green before fix"
        )


class TestKgSnapshotCheckIsBehavioral:
    """The KG check must require a POPULATED graph, not just a present (possibly
    side-effect-created, empty) context_graph.db — else it false-greens."""

    @staticmethod
    def _make_db(path, node_count: int) -> None:
        import sqlite3

        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE nodes (id TEXT)")
        conn.executemany("INSERT INTO nodes VALUES (?)", [(str(i),) for i in range(node_count)])
        conn.commit()
        conn.close()

    def test_empty_kg_db_fails(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        self._make_db(tmp_path / ".storage" / "opencontext" / "context_graph.db", 0)
        passed, explanation = MetaHarnessScanner(root=tmp_path)._check_kg_snapshot_path()
        assert passed is False
        assert "empty" in explanation.lower()

    def test_missing_kg_fails(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        passed, _ = MetaHarnessScanner(root=tmp_path)._check_kg_snapshot_path()
        assert passed is False

    def test_populated_kg_db_passes(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        self._make_db(tmp_path / ".storage" / "opencontext" / "context_graph.db", 3)
        passed, explanation = MetaHarnessScanner(root=tmp_path)._check_kg_snapshot_path()
        assert passed is True
        assert "3 node" in explanation
