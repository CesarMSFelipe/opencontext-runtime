"""Black-box CLI invocation helpers for the acceptance suite.

Every acceptance test drives the real ``opencontext`` binary through
:func:`run` / :func:`run_json`. Nothing here imports product code — that is
the whole point of the suite (ACCEPTANCE_CONTRACT.md).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

#: Default per-command timeout (seconds). Workflow runs pass a larger value.
DEFAULT_TIMEOUT = 120


def run(
    oc_bin: str,
    args: list[str],
    *,
    cwd: Path | str,
    env: dict[str, str],
    timeout: int = DEFAULT_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    """Invoke the ``opencontext`` binary as a real user would (subprocess only)."""
    return subprocess.run(
        [oc_bin, *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def run_json(
    oc_bin: str,
    args: list[str],
    *,
    cwd: Path | str,
    env: dict[str, str],
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[subprocess.CompletedProcess[str], Any]:
    """Invoke the binary and enforce the JSON purity rule (CLI_CONTRACT.md).

    stdout must contain ONLY one parseable JSON document; any human-facing
    text mixed into stdout is a contract violation and fails the calling test.
    """
    proc = run(oc_bin, args, cwd=cwd, env=env, timeout=timeout)
    payload = parse_pure_json_stdout(proc)
    return proc, payload


def parse_pure_json_stdout(proc: subprocess.CompletedProcess[str]) -> Any:
    """Assert stdout is exactly one JSON document and return it parsed."""
    stdout = proc.stdout
    assert stdout.strip(), (
        "CLI_CONTRACT JSON purity: expected a JSON document on stdout, got empty stdout. "
        f"cmd={proc.args!r} exit={proc.returncode} stderr={proc.stderr[:500]!r}"
    )
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - assertion path
        raise AssertionError(
            "CLI_CONTRACT JSON purity: stdout is not a single clean JSON document "
            f"({exc}). cmd={proc.args!r} stdout[:800]={stdout[:800]!r}"
        ) from None
