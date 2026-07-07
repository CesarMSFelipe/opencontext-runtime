"""CLI truth layer: canonical exit codes, JSON envelopes, and command maturity.

Dependency-free by design so any command (and the acceptance harness) can
import it without pulling in the runtime.
"""

from opencontext_cli.contracts.error_envelope import error_envelope, success_envelope
from opencontext_cli.contracts.errors import CliContractError
from opencontext_cli.contracts.exit_codes import ExitCode, exit_code_for_status

__all__ = [
    "CliContractError",
    "ExitCode",
    "error_envelope",
    "exit_code_for_status",
    "success_envelope",
]
