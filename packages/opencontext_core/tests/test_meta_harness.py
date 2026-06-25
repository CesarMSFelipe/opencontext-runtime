"""Tests for D6: MetaHarnessScanner, report scoring, and independence."""

from __future__ import annotations

from opencontext_core.harness.meta import MetaHarnessCheck, MetaHarnessReport, MetaHarnessScanner


class TestMetaHarnessReport:
    def test_all_pass_score_100(self) -> None:
        checks = [
            MetaHarnessCheck(name=f"check_{i}", passed=True, score_contribution=w, explanation="OK")
            for i, w in enumerate([12, 11, 11, 11, 11, 11, 11, 11, 11])
        ]
        report = MetaHarnessReport.from_checks(checks)
        assert report.score == 100
        assert report.passed is True

    def test_one_fail_drops_below_90(self) -> None:
        # 8 pass x 11 = 88 (the check with weight 12 fails)
        checks = [
            MetaHarnessCheck(
                name="big_check", passed=False, score_contribution=0, explanation="fail"
            ),
        ]
        checks = [
            *checks,
            *[
                MetaHarnessCheck(
                    name=f"check_{i}", passed=True, score_contribution=11, explanation="OK"
                )
                for i in range(8)
            ],
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
    def test_scan_returns_9_checks(self) -> None:
        scanner = MetaHarnessScanner()
        report = scanner.scan()
        assert len(report.checks) == 9

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
        }
        assert names == expected

    def test_exception_in_one_check_does_not_stop_others(self) -> None:
        """Monkey-patch one check to raise; all 9 checks must still run."""
        scanner = MetaHarnessScanner()
        original = scanner._check_memory_backend

        def _raises() -> tuple[bool, str]:
            raise RuntimeError("simulated check failure")

        scanner._check_memory_backend = _raises  # type: ignore[method-assign]
        report = scanner.scan()
        assert len(report.checks) == 9
        failing = next(c for c in report.checks if c.name == "memory_backend")
        assert failing.passed is False
        assert "simulated check failure" in failing.explanation

        scanner._check_memory_backend = original  # type: ignore[method-assign]

    def test_weights_sum_to_100(self) -> None:
        from opencontext_core.harness.meta import _WEIGHTS

        assert sum(_WEIGHTS) == 100
        assert len(_WEIGHTS) == 9


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
        passed, explanation = MetaHarnessScanner()._check_kg_snapshot_path()
        assert passed is False
        assert "empty" in explanation.lower()

    def test_missing_kg_fails(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        passed, _ = MetaHarnessScanner()._check_kg_snapshot_path()
        assert passed is False

    def test_populated_kg_db_passes(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        self._make_db(tmp_path / ".storage" / "opencontext" / "context_graph.db", 3)
        passed, explanation = MetaHarnessScanner()._check_kg_snapshot_path()
        assert passed is True
        assert "3 node" in explanation
