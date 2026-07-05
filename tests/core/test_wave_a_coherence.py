"""Regression guards for the functional-validation Wave A fixes.

Each test pins a bug a multiagent validation run confirmed against the real product:
- compliance_matrix config flag was unsettable (schema extra=forbid, no verify field)
- `opencontext maturity` / `maturity --json` exited 2 instead of running assess
- harness silently dropped declared gates that have no dispatch binding
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest


def test_verify_compliance_matrix_config_is_settable() -> None:
    """A `verify: {compliance_matrix: true}` block must load, not raise extra-forbid."""
    from opencontext_core.config import OpenContextConfig, VerifyConfig

    assert VerifyConfig(compliance_matrix=True).compliance_matrix is True
    # Default off preserves prior behaviour.
    assert OpenContextConfig.model_fields["verify"].default_factory().compliance_matrix is False


def test_maturity_bare_and_json_do_not_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    """Bare `maturity` and `maturity --json` run assess (were argparse exit 2)."""
    from opencontext_cli.commands.maturity_cmd import handle_maturity

    # maturity_command is None (bare invocation) — must NOT sys.exit(2).
    handle_maturity(SimpleNamespace(maturity_command=None, root=".", json=True, output=None))
    out = capsys.readouterr().out
    assert '"overall_level"' in out or "overall_level" in out


def test_maturity_rejects_unknown_subcommand() -> None:
    from opencontext_cli.commands.maturity_cmd import handle_maturity

    with pytest.raises(SystemExit) as exc:
        handle_maturity(SimpleNamespace(maturity_command="bogus", root=".", json=False))
    assert exc.value.code == 2


def test_harness_warns_on_unbound_declared_gate(caplog: pytest.LogCaptureFixture) -> None:
    """A declared gate with no dispatch binding must be reported, not silently dropped."""
    from opencontext_core.harness import runner as runner_mod

    r = runner_mod.HarnessRunner.__new__(runner_mod.HarnessRunner)
    phase_config = SimpleNamespace(gates=["definitely_not_a_bound_gate_xyz"])
    # An unbound gate id short-circuits to None before any state access, so a
    # lightweight stand-in for result/state is enough to exercise the warning.
    result = SimpleNamespace(gates=[])
    state = SimpleNamespace(root=".")
    with caplog.at_level(logging.WARNING, logger=runner_mod.__name__):
        dispatched = runner_mod.HarnessRunner._dispatch_declared_gates(
            r, state, "verify", phase_config, result
        )
    assert dispatched == []  # no fabricated gate
    assert any("no dispatch binding" in rec.message for rec in caplog.records)
    assert any("definitely_not_a_bound_gate_xyz" in str(rec.args) for rec in caplog.records)
