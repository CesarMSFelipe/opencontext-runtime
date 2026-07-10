"""REQ-07: benchmark run/list exits non-zero with clear message when suite is absent."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def _make_run_args(suite: str) -> SimpleNamespace:
    return SimpleNamespace(
        benchmark_command="run",
        suite=suite,
        case=None,
        category=None,
        root=".",
        max_tokens=6000,
        format="text",
        output=None,
        save=False,
        no_refresh=False,
    )


def _make_list_args(suite: str) -> SimpleNamespace:
    return SimpleNamespace(
        benchmark_command="list",
        suite=suite,
        case=None,
        category=None,
    )


def test_benchmark_run_exits_nonzero_when_suite_missing(tmp_path) -> None:
    """benchmark run exits non-zero when --suite path does not exist."""
    from opencontext_cli.commands.benchmark_cmd import _handle_run

    nonexistent = str(tmp_path / "no-such-suite.yaml")
    args = _make_run_args(suite=nonexistent)

    import io
    from contextlib import redirect_stderr

    err_buf = io.StringIO()
    with pytest.raises(SystemExit) as exc_info:
        with redirect_stderr(err_buf):
            _handle_run(args)

    assert exc_info.value.code != 0
    stderr_text = err_buf.getvalue()
    assert "--suite is required outside the development repository" in stderr_text


def test_benchmark_list_exits_nonzero_when_suite_missing(tmp_path) -> None:
    """benchmark list exits non-zero when --suite path does not exist."""
    from opencontext_cli.commands.benchmark_cmd import _handle_list

    nonexistent = str(tmp_path / "no-such-suite.yaml")
    args = _make_list_args(suite=nonexistent)

    import io
    from contextlib import redirect_stderr

    err_buf = io.StringIO()
    with pytest.raises(SystemExit) as exc_info:
        with redirect_stderr(err_buf):
            _handle_list(args)

    assert exc_info.value.code != 0
    assert "--suite is required outside the development repository" in err_buf.getvalue()
