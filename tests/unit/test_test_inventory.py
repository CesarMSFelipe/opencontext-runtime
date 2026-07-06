"""Unit tests for scripts/test_inventory.py (plan §26.1/§26.2 static inventory).

Pure-logic coverage: source analysis heuristics, classification rules, and the
duplicate-stem merge pass. No filesystem walking is exercised here.
"""

from __future__ import annotations

from scripts.test_inventory import (
    analyze_source,
    apply_merge_pass,
    classify,
    normalized_stem,
    render_markdown,
)


def _record(**overrides: object) -> dict:
    base: dict = {
        "path": "tests/unit/test_sample.py",
        "suite": "unit",
        "test_count": 1,
        "markers": [],
        "uses_mock": False,
        "uses_filesystem": False,
        "uses_subprocess": False,
    }
    base.update(overrides)
    return base


class TestAnalyzeSource:
    def test_counts_sync_and_async_test_functions(self) -> None:
        source = (
            "def test_one():\n    pass\n\n"
            "async def test_two():\n    pass\n\n"
            "def helper():\n    pass\n\n"
            "class TestThing:\n"
            "    def test_three(self):\n        pass\n"
        )
        record = analyze_source("tests/unit/test_x.py", source)
        assert record["test_count"] == 3

    def test_suite_is_first_dir_under_tests(self) -> None:
        record = analyze_source("tests/oc_flow/test_x.py", "def test_a():\n    pass\n")
        assert record["suite"] == "oc_flow"

    def test_root_level_file_gets_root_suite(self) -> None:
        record = analyze_source("tests/test_x.py", "def test_a():\n    pass\n")
        assert record["suite"] == "(root)"

    def test_collects_marker_names(self) -> None:
        source = (
            "import pytest\n\n"
            "@pytest.mark.smoke\n"
            "@pytest.mark.acceptance\n"
            "def test_a():\n    pass\n\n"
            "@pytest.mark.xfail(reason='GAP-001: pending')\n"
            "def test_b():\n    pass\n"
        )
        record = analyze_source("tests/acceptance/test_x.py", source)
        assert record["markers"] == ["acceptance", "smoke", "xfail"]

    def test_detects_mock_imports(self) -> None:
        for line in (
            "from unittest.mock import MagicMock",
            "from unittest import mock",
            "import unittest.mock",
        ):
            record = analyze_source("tests/unit/test_x.py", f"{line}\n\ndef test_a():\n    pass\n")
            assert record["uses_mock"] is True, line

    def test_no_mock_when_absent(self) -> None:
        record = analyze_source("tests/unit/test_x.py", "def test_a():\n    pass\n")
        assert record["uses_mock"] is False

    def test_detects_filesystem_usage(self) -> None:
        source = "def test_a(tmp_path):\n    (tmp_path / 'f').write_text('x')\n"
        record = analyze_source("tests/unit/test_x.py", source)
        assert record["uses_filesystem"] is True

    def test_detects_subprocess_usage(self) -> None:
        source = "import subprocess\n\ndef test_a():\n    subprocess.run(['true'])\n"
        record = analyze_source("tests/unit/test_x.py", source)
        assert record["uses_subprocess"] is True

    def test_pure_file_has_no_io_flags(self) -> None:
        record = analyze_source("tests/unit/test_x.py", "def test_a():\n    assert 1 + 1 == 2\n")
        assert record["uses_filesystem"] is False
        assert record["uses_subprocess"] is False


class TestClassify:
    def test_acceptance_suite(self) -> None:
        label, _ = classify(_record(suite="acceptance", path="tests/acceptance/test_x.py"))
        assert label == "KEEP_ACCEPTANCE"

    def test_golden_suite_is_contract(self) -> None:
        label, _ = classify(_record(suite="golden", path="tests/golden/test_x.py"))
        assert label == "KEEP_CONTRACT"

    def test_compat_suite_is_contract(self) -> None:
        label, _ = classify(_record(suite="compat", path="tests/compat/test_x.py"))
        assert label == "KEEP_CONTRACT"

    def test_done_in_v1_is_quarantine(self) -> None:
        label, _ = classify(_record(suite="done_in_v1", path="tests/done_in_v1/test_x.py"))
        assert label == "QUARANTINE"

    def test_flaky_marker_is_quarantine(self) -> None:
        label, _ = classify(_record(markers=["flaky"]))
        assert label == "QUARANTINE"

    def test_mock_only_is_delete_candidate(self) -> None:
        label, reasons = classify(_record(uses_mock=True))
        assert label == "DELETE"
        assert any("mock" in reason for reason in reasons)

    def test_mock_plus_subprocess_is_not_delete(self) -> None:
        label, _ = classify(_record(uses_mock=True, uses_subprocess=True))
        assert label != "DELETE"

    def test_integration_suite_is_boundary(self) -> None:
        label, _ = classify(_record(suite="integration", path="tests/integration/test_x.py"))
        assert label == "KEEP_INTEGRATION_BOUNDARY"

    def test_regression_signal_wins_over_unit(self) -> None:
        label, _ = classify(_record(requirement_ids=["GAP-012"]))
        assert label == "KEEP_REGRESSION"

    def test_pure_unit_file_is_unit_critical(self) -> None:
        label, _ = classify(_record())
        assert label == "KEEP_UNIT_CRITICAL"

    def test_io_touching_misc_suite_is_boundary(self) -> None:
        label, _ = classify(_record(suite="cli", path="tests/cli/test_x.py", uses_filesystem=True))
        assert label == "KEEP_INTEGRATION_BOUNDARY"


class TestMergePass:
    def test_duplicate_stem_marks_internal_file_as_merge(self) -> None:
        internal = _record(path="tests/unit/test_pack.py", suite="unit")
        external = _record(path="tests/acceptance/test_pack.py", suite="acceptance")
        for record in (internal, external):
            record["classification"], record["reasons"] = classify(record)
        apply_merge_pass([internal, external])
        assert internal["classification"] == "MERGE"
        assert external["classification"] == "KEEP_ACCEPTANCE"

    def test_unique_stems_untouched(self) -> None:
        record = _record(path="tests/unit/test_alone.py")
        record["classification"], record["reasons"] = classify(record)
        apply_merge_pass([record])
        assert record["classification"] == "KEEP_UNIT_CRITICAL"

    def test_normalized_stem_strips_test_prefix(self) -> None:
        assert normalized_stem("tests/unit/test_pack.py") == "pack"
        assert normalized_stem("tests/cli/test_pack.py") == "pack"


class TestRenderMarkdown:
    def test_summary_contains_suite_and_candidate_sections(self) -> None:
        records = [_record(path="tests/unit/test_a.py", uses_mock=True)]
        for record in records:
            record["classification"], record["reasons"] = classify(record)
        inventory = {
            "total_files": 1,
            "total_tests": 1,
            "files": records,
        }
        output = render_markdown(inventory)
        assert "| Suite |" in output
        assert "DELETE candidates" in output
        assert "tests/unit/test_a.py" in output
