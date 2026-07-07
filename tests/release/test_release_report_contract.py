"""REL-GATE: release report field contract + gate exit code (plan §17.4).

``scripts/release_report.py`` is the last stage of the release gate
(release-acceptance.yml): it must emit a report containing the version, a
real checksum per artifact, the acceptance summary parsed from the gate's
pytest log, and the known limitations — and it must exit nonzero whenever
any gate stage failed. ``tests/unit/test_release_report.py`` covers only the
pure parsing helpers; these tests invoke ``main()`` end-to-end so the report
FIELD contract and the gate exit code cannot silently regress.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from scripts.release_report import main

_PASSING_LOG = (
    "XFAIL tests/acceptance/test_x.py::test_a - GAP-101: pack metrics missing\n"
    "41 passed, 1 xfailed in 208.51s (0:03:28)\n"
)
_FAILING_LOG = "1 failed, 40 passed in 199.00s\n"


@pytest.fixture()
def artifact(tmp_path: Path) -> Path:
    wheel = tmp_path / "opencontext_cli-9.9.9-py3-none-any.whl"
    wheel.write_bytes(b"wheel-bytes-under-test")
    return wheel


def _run_main(
    tmp_path: Path,
    artifact: Path,
    *,
    log: str = _PASSING_LOG,
    hygiene_exit: int = 0,
    uninstall_exit: int = 0,
    limitations: list[str] | None = None,
) -> tuple[int, dict]:
    log_path = tmp_path / "acceptance.log"
    log_path.write_text(log, encoding="utf-8")
    output = tmp_path / "artifacts" / "release-report.json"
    argv = [
        "--version",
        "9.9.9",
        "--artifact",
        str(artifact),
        "--hygiene-exit",
        str(hygiene_exit),
        "--acceptance-log",
        str(log_path),
        "--acceptance-oc-bin",
        "/tmp/venv/bin/opencontext",
        "--uninstall-exit",
        str(uninstall_exit),
        "--output",
        str(output),
    ]
    for text in limitations or []:
        argv += ["--limitation", text]
    exit_code = main(argv)
    report = json.loads(output.read_text(encoding="utf-8")) if output.is_file() else {}
    return exit_code, report


def test_report_contains_version_checksums_acceptance_summary_and_limitations(
    tmp_path: Path, artifact: Path
) -> None:
    """REL-GATE: the report carries version, per-artifact sha256, acceptance
    summary and known limitations — the §17.4 field contract."""
    exit_code, report = _run_main(
        tmp_path, artifact, limitations=["provider-free verification only"]
    )
    assert exit_code == 0

    assert report["version"] == "9.9.9"
    assert report["generated_at"]

    expected_sha = hashlib.sha256(b"wheel-bytes-under-test").hexdigest()
    assert report["artifacts"] == [{"name": artifact.name, "sha256": expected_sha}]

    acceptance = report["acceptance"]
    assert acceptance["passed"] == 41
    assert acceptance["failed"] == 0
    assert acceptance["xfailed"] == 1
    assert acceptance["remaining_gaps"] == ["GAP-101"]
    assert acceptance["oc_bin"] == "/tmp/venv/bin/opencontext"

    assert report["hygiene"] == "pass"
    assert report["uninstall_verify"] == "pass"
    # Known limitations = still-open gaps plus explicitly declared ones.
    assert report["known_limitations"] == ["GAP-101", "provider-free verification only"]


def test_gate_exits_nonzero_when_acceptance_failed(tmp_path: Path, artifact: Path) -> None:
    """REL-GATE: any acceptance failure in the gate log makes the report stage
    exit nonzero, so publish cannot proceed on a red acceptance run."""
    exit_code, report = _run_main(tmp_path, artifact, log=_FAILING_LOG)
    assert exit_code != 0
    # The report is still written (evidence), but records the failure honestly.
    assert report["acceptance"]["failed"] == 1


@pytest.mark.parametrize(
    ("hygiene_exit", "uninstall_exit"),
    [(1, 0), (0, 1)],
    ids=["hygiene-fail", "uninstall-fail"],
)
def test_gate_exits_nonzero_when_a_stage_failed(
    tmp_path: Path, artifact: Path, hygiene_exit: int, uninstall_exit: int
) -> None:
    """REL-GATE: a failed hygiene audit or uninstall-verify stage is reported
    as fail and forces a nonzero gate exit."""
    exit_code, report = _run_main(
        tmp_path, artifact, hygiene_exit=hygiene_exit, uninstall_exit=uninstall_exit
    )
    assert exit_code != 0
    expected = "fail" if hygiene_exit else "pass"
    assert report["hygiene"] == expected
    expected = "fail" if uninstall_exit else "pass"
    assert report["uninstall_verify"] == expected


def test_gate_exits_nonzero_when_log_has_no_summary(tmp_path: Path, artifact: Path) -> None:
    """REL-GATE: a log without a pytest summary line cannot produce a report —
    acceptance numbers are parsed, never invented."""
    exit_code, report = _run_main(tmp_path, artifact, log="...... [100%]\n")
    assert exit_code != 0
    assert report == {}, "no report may be written from an unparseable log"


def test_gate_exits_nonzero_when_artifact_is_missing(tmp_path: Path) -> None:
    """REL-GATE: a declared-but-missing artifact fails the report stage instead
    of publishing a report with fabricated checksums."""
    exit_code, report = _run_main(tmp_path, tmp_path / "not-built.whl")
    assert exit_code != 0
    assert report == {}
