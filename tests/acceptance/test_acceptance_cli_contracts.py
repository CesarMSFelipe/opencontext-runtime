"""AC-001 / AC-002 / AC-024: CLI truth — clean JSON, actionable errors, envelopes.

Contracts: CLI_CONTRACT.md (JSON purity, error envelope, exit codes),
ACCEPTANCE_CONTRACT.md.
"""

from __future__ import annotations

import pytest

from tests.acceptance.helpers.cli import run, run_json
from tests.acceptance.helpers.json_assertions import (
    assert_error_envelope,
    assert_no_ansi,
    assert_semver,
)

pytestmark = pytest.mark.acceptance


@pytest.mark.smoke
def test_version_json_is_clean_and_real(oc_bin, workspace) -> None:
    """AC-001: `version --json` returns the real version as clean JSON."""
    ws = workspace()
    proc, payload = run_json(oc_bin, ["version", "--json"], cwd=ws.root, env=ws.env)
    assert proc.returncode == 0, proc.stderr
    assert_no_ansi(proc.stdout, where="version --json stdout")
    assert isinstance(payload, dict)
    assert "opencontext" in payload, f"version block missing 'opencontext' key: {payload}"
    assert_semver(payload["opencontext"], where="version --json .opencontext")


@pytest.mark.smoke
def test_doctor_json_is_parseable_and_pure(oc_bin, workspace) -> None:
    """AC-002: `doctor --json` is parseable and mixes no human text into stdout."""
    ws = workspace("py_bugfix_basic")
    proc, payload = run_json(oc_bin, ["doctor", "--json", "runtime"], cwd=ws.root, env=ws.env)
    assert proc.returncode == 0, proc.stderr
    assert_no_ansi(proc.stdout, where="doctor --json stdout")
    assert isinstance(payload, dict)
    # The report is structured: a scope plus per-check results.
    assert payload.get("scope") == "runtime"
    checks = payload.get("checks")
    assert isinstance(checks, list) and checks, f"doctor reported no checks: {payload}"
    assert isinstance(payload.get("passed"), int)
    assert isinstance(payload.get("failed"), int)


def test_common_errors_are_actionable(oc_bin, workspace) -> None:
    """AC-024: common errors are actionable — hint on stderr, clean streams, usage exit code."""
    ws = workspace("py_bugfix_basic")

    # Unknown command → CLI usage error, exit code 2 (CLI_CONTRACT exit codes).
    proc = run(oc_bin, ["definitely-not-a-command"], cwd=ws.root, env=ws.env)
    assert proc.returncode == 2, f"usage errors must exit 2, got {proc.returncode}"

    # pack on a root that cannot be indexed → non-zero exit + an actionable
    # corrective command on stderr (never a stack trace, never stdout garbage).
    # Human mode: JSON mode emits the error envelope instead (envelope test below).
    missing_root = ws.root / "does-not-exist"
    proc = run(
        oc_bin,
        ["pack", str(missing_root), "--query", "explain this project"],
        cwd=ws.root,
        env=ws.env,
    )
    assert proc.returncode != 0, "pack on a nonexistent root must fail"
    assert "opencontext index" in proc.stderr, (
        f"error must name the corrective command (`opencontext index`), got: {proc.stderr[:400]}"
    )
    assert "Traceback" not in proc.stderr, f"raw traceback leaked: {proc.stderr[:400]}"
    assert not proc.stdout.strip(), (
        f"a failed pack must not emit partial output on stdout: {proc.stdout[:200]!r}"
    )


def test_json_failures_return_stable_error_envelope(oc_bin, workspace) -> None:
    """AC-024: failing commands in JSON mode return the stable error envelope."""
    ws = workspace("py_bugfix_basic")
    # A common failure: packing a root that does not exist / cannot be indexed.
    missing_root = ws.root / "does-not-exist"
    proc, payload = run_json(
        oc_bin,
        ["pack", str(missing_root), "--query", "explain this project", "--format", "json"],
        cwd=ws.root,
        env=ws.env,
    )
    assert proc.returncode != 0
    assert_error_envelope(payload)
    assert payload["error"].get("hint"), "P0 errors must carry an actionable hint"
