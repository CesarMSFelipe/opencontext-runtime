"""R2: `opencontext run` prints a pre-run cost estimate hint to stderr.

Failing tests:
- stderr carries a hint line with token/cost information before the run.
- --json stdout stays pure JSON (parseable by json.loads).
- An estimate failure causes a silent skip, not a crash.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from opencontext_cli.commands.run_cmd import handle_run_exec


def _args(tmp_path: Path, *, json_out: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        task="Fix failing test",
        workflow="oc-flow",
        lane="fast",
        profile="balanced",
        resume=None,
        root=str(tmp_path),
        config=None,
        json=json_out,
    )


def _make_stub_api(status: str = "completed") -> type:
    class _FakeLegacy:
        workflow_selection: dict[str, str] = {}  # noqa: RUF012

    class _FakeResult:
        run_id = "r-cost-test"
        legacy = _FakeLegacy()

    _FakeResult.status = status  # type: ignore[attr-defined]
    _FakeLegacy.status = status  # type: ignore[attr-defined]

    class _FakeSession:
        session_id = "sess-cost-test"
        status = "created"
        session_path = "/tmp/s"

    class _FakeApi:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def start_session(self, request: Any) -> Any:
            return _FakeSession()

        def run(self, request: Any) -> Any:
            return _FakeResult()

    return _FakeApi


def test_cost_hint_appears_on_stderr(tmp_path: Path, capsys: Any) -> None:
    """A pre-run cost estimate marker '[oc] estimate:' must appear on stderr."""
    # Write a minimal project config so missing_config_hint is NOT printed,
    # giving us a clean stderr to inspect.
    (tmp_path / "opencontext.yaml").write_text("{}", encoding="utf-8")

    with patch("opencontext_core.runtime.api.RuntimeApi", _make_stub_api()):
        handle_run_exec(_args(tmp_path))

    err = capsys.readouterr().err
    # The implementation will print a line like: "[oc] estimate: ~4200 tokens …"
    assert "[oc] estimate:" in err, (
        f"Expected '[oc] estimate:' cost hint on stderr.\nGot stderr:\n{err!r}"
    )


def test_cost_hint_does_not_corrupt_json_stdout(tmp_path: Path, capsys: Any) -> None:
    """--json stdout must remain pure JSON even when the cost hint is emitted."""
    (tmp_path / "opencontext.yaml").write_text("{}", encoding="utf-8")

    with patch("opencontext_core.runtime.api.RuntimeApi", _make_stub_api()):
        handle_run_exec(_args(tmp_path, json_out=True))

    captured = capsys.readouterr()
    # stdout must be valid JSON
    payload = json.loads(captured.out)
    assert "status" in payload, f"Unexpected JSON shape: {payload}"
    # hint must be on stderr, not stdout
    assert "[oc] estimate:" in captured.err, (
        f"Expected '[oc] estimate:' on stderr.\nGot:\n{captured.err!r}"
    )


def test_cost_hint_failure_does_not_crash(tmp_path: Path, capsys: Any) -> None:
    """An estimate error must be silently skipped — handle_run_exec must not raise."""
    (tmp_path / "opencontext.yaml").write_text("{}", encoding="utf-8")

    with (
        patch("opencontext_core.runtime.api.RuntimeApi", _make_stub_api()),
        patch(
            "opencontext_core.runtime_intelligence.cost.CostEngine.estimate",
            side_effect=RuntimeError("intentional failure"),
        ),
    ):
        handle_run_exec(_args(tmp_path))  # must not raise

    captured = capsys.readouterr()
    # The run must still complete; stdout must have the run summary
    assert captured.out, "Expected run summary on stdout even when estimate fails"
    # No "[oc] estimate:" line when estimate fails (silent skip)
    assert "[oc] estimate:" not in captured.err, (
        "Estimate failure must be silently skipped, not propagated to stderr"
    )
