from __future__ import annotations

from pathlib import Path

from opencontext_core.operating_model import ReleaseLeakScanner


def test_release_leak_scanner_detects_source_map(tmp_path: Path) -> None:
    (tmp_path / "app.js.map").write_text("{}", encoding="utf-8")

    report = ReleaseLeakScanner().scan(tmp_path)

    assert any(finding.kind == "source_map_file" for finding in report.findings)


def test_release_leak_scanner_prunes_virtualenv_trees(tmp_path: Path) -> None:
    # Regression: the nightly release gate blocked forever because the scan walked
    # into a CI-created virtualenv (.ci-venv) and flagged secret-like patterns in
    # third-party site-packages. Any *venv* / site-packages tree must be pruned.
    leak = "AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE\n"
    venv_file = tmp_path / ".ci-venv" / "lib" / "site-packages" / "dep.py"
    venv_file.parent.mkdir(parents=True)
    venv_file.write_text(leak, encoding="utf-8")

    report = ReleaseLeakScanner().scan(tmp_path)

    assert not report.blocked
    assert not report.findings
