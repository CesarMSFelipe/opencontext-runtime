"""End-to-end tests for the honest efficiency benchmark (CON vs realistic SIN).

These exercise the real ``runtime.prepare_context`` (no fabricated inputs, no model
calls) on a tmp project, the real grep+Read SIN, and the mandatory quality-parity
gate. They pin the acceptance scenarios EB-1, EB-3, EB-4, EB-6, EB-7.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from opencontext_core.evaluation.efficiency import (
    EfficiencyBenchmark,
    format_efficiency_report,
    format_efficiency_report_json,
    load_last_efficiency_result,
    save_efficiency_result,
)
from opencontext_core.evaluation.models import (
    ContextBenchCase,
    EfficiencyCaseResult,
    EfficiencyReport,
)
from opencontext_core.runtime import OpenContextRuntime


def _project(tmp_path: Path) -> OpenContextRuntime:
    (tmp_path / "auth.py").write_text(
        "def authenticate_user(token: str) -> bool:\n"
        "    '''Validate a session token.'''\n"
        "    return token == 'test-token'\n",
        encoding="utf-8",
    )
    (tmp_path / "login.py").write_text(
        "from auth import authenticate_user\n\n\n"
        "def login(token: str) -> str:\n"
        "    return 'ok' if authenticate_user(token) else 'deny'\n",
        encoding="utf-8",
    )
    (tmp_path / "billing.py").write_text(
        "def invoice(customer: str) -> int:\n    return 42\n",
        encoding="utf-8",
    )
    runtime = OpenContextRuntime(storage_path=tmp_path / ".storage" / "opencontext")
    runtime.index_project(tmp_path)
    return runtime


def _auth_case() -> ContextBenchCase:
    return ContextBenchCase(
        id="auth-source",
        query="Where is authenticate_user implemented and who calls it?",
        expected_sources=["auth.py"],
        forbidden_sources=[".storage/"],
        min_source_coverage=1.0,
        target_symbol="authenticate_user",
        difficulty="simple",
    )


class TestConHonestCost:
    """EB-1: CON cost comes from the REAL prepare_context, tool_calls == 1."""

    def test_con_triple_is_real(self, tmp_path: Path) -> None:
        runtime = _project(tmp_path)
        bench = EfficiencyBenchmark(runtime, root=tmp_path, max_tokens=2000)
        result = bench.evaluate_case(_auth_case())

        assert isinstance(result, EfficiencyCaseResult)
        assert result.con.tokens > 0
        assert result.con.tool_calls == 1  # the single prepare_context call, stated honestly
        assert result.con.latency_ms >= 0.0

    def test_symmetry_con_and_sin_same_fields(self, tmp_path: Path) -> None:
        """EB-3: CON and SIN report the same three fields in the same units."""
        runtime = _project(tmp_path)
        bench = EfficiencyBenchmark(runtime, root=tmp_path, max_tokens=2000)
        result = bench.evaluate_case(_auth_case())

        for triple in (result.con, result.sin):
            assert triple.tokens >= 0
            assert triple.tool_calls >= 0
            assert triple.latency_ms >= 0.0
        # SIN greps + reads at least auth.py and login.py.
        assert result.sin.tool_calls >= 2


class TestParityMandatory:
    """EB-4 / R4: a CON pack missing an expected source is insufficient, not a win."""

    def test_missing_expected_source_is_insufficient(self, tmp_path: Path) -> None:
        runtime = _project(tmp_path)
        bench = EfficiencyBenchmark(runtime, root=tmp_path, max_tokens=2000)
        impossible = ContextBenchCase(
            id="impossible",
            query="Where is authenticate_user implemented?",
            expected_sources=["does_not_exist_anywhere.py"],
            min_source_coverage=1.0,
            target_symbol="authenticate_user",
        )
        result = bench.evaluate_case(impossible)
        assert result.con_sufficient is False
        assert result.source_coverage < 1.0

    def test_forbidden_hit_is_insufficient(self, tmp_path: Path) -> None:
        runtime = _project(tmp_path)
        bench = EfficiencyBenchmark(runtime, root=tmp_path, max_tokens=2000)
        forbid_auth = ContextBenchCase(
            id="forbid",
            query="Where is authenticate_user implemented?",
            expected_sources=["auth.py"],
            forbidden_sources=["auth.py"],  # contradictory on purpose
            min_source_coverage=1.0,
            target_symbol="authenticate_user",
        )
        result = bench.evaluate_case(forbid_auth)
        # If auth.py is included it satisfies coverage but trips the forbidden gate.
        if "auth.py" in " ".join(result.forbidden_hits):
            assert result.con_sufficient is False


class TestSuiteAndAggregates:
    def test_suite_builds_report(self, tmp_path: Path) -> None:
        runtime = _project(tmp_path)
        bench = EfficiencyBenchmark(runtime, root=tmp_path, max_tokens=2000)
        report = bench.evaluate_suite([_auth_case()])
        assert isinstance(report, EfficiencyReport)
        assert len(report.cases) == 1
        assert report.con_latency_p(50) >= 0.0

    def test_reproducible_tokens_and_tool_calls(self, tmp_path: Path) -> None:
        """EB-7: two passes on one pinned index → identical tokens + tool_calls."""
        runtime = _project(tmp_path)
        bench = EfficiencyBenchmark(runtime, root=tmp_path, max_tokens=2000)
        first = bench.evaluate_case(_auth_case())
        second = bench.evaluate_case(_auth_case())
        assert first.con.tokens == second.con.tokens
        assert first.con.tool_calls == second.con.tool_calls
        assert first.sin.tokens == second.sin.tokens
        assert first.sin.tool_calls == second.sin.tool_calls


class TestNoBakedClaim:
    """EB-6 / ED8: report (text/json) carries NO '%'/badge/claim string."""

    DENY = re.compile(r"%|reduction_pct|\bbadge\b|\bclaim\b|fewer tokens|faster", re.IGNORECASE)

    def test_text_report_has_no_claim(self, tmp_path: Path) -> None:
        runtime = _project(tmp_path)
        bench = EfficiencyBenchmark(runtime, root=tmp_path, max_tokens=2000)
        report = bench.evaluate_suite([_auth_case()])
        text = format_efficiency_report(report)
        assert not self.DENY.search(text), f"claim-like token in report:\n{text}"

    def test_json_report_has_no_claim(self, tmp_path: Path) -> None:
        runtime = _project(tmp_path)
        bench = EfficiencyBenchmark(runtime, root=tmp_path, max_tokens=2000)
        report = bench.evaluate_suite([_auth_case()])
        payload = format_efficiency_report_json(report)
        # valid JSON, and no claim field
        parsed = json.loads(payload)
        assert "cases" in parsed
        assert not self.DENY.search(payload), f"claim-like token in JSON:\n{payload}"


class TestPersistenceRoundTrip:
    def test_save_and_load(self, tmp_path: Path) -> None:
        runtime = _project(tmp_path)
        bench = EfficiencyBenchmark(runtime, root=tmp_path, max_tokens=2000)
        report = bench.evaluate_suite([_auth_case()])
        out_dir = tmp_path / "benchmarks"
        path = save_efficiency_result(report, directory=out_dir)
        assert path.exists()
        loaded = load_last_efficiency_result(directory=out_dir)
        assert loaded is not None
        assert len(loaded.cases) == len(report.cases)
        assert loaded.cases[0].con.tool_calls == report.cases[0].con.tool_calls

    def test_load_none_when_empty(self, tmp_path: Path) -> None:
        assert load_last_efficiency_result(directory=tmp_path / "nope") is None
