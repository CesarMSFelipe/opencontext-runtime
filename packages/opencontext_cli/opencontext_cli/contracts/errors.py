"""Contract-aware CLI error for uniform dispatcher handling."""

from __future__ import annotations

from typing import Any

from opencontext_cli.contracts.error_envelope import error_envelope
from opencontext_cli.contracts.exit_codes import exit_code_for_status


class CliContractError(Exception):
    """Raise from a command to fail with a standard envelope and exit code.

    The top-level dispatcher renders it: pure JSON on stdout under ``--json``,
    a human message on stderr otherwise, exiting with
    ``exit_code_for_status(status)`` unless *exit_code* overrides it.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str | None = None,
        details: dict[str, Any] | None = None,
        status: str = "failed",
        exit_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details
        self.status = status
        self.exit_code = exit_code if exit_code is not None else exit_code_for_status(status)

    def to_envelope(self) -> dict[str, Any]:
        return error_envelope(
            self.code,
            self.message,
            hint=self.hint,
            details=self.details,
            status=self.status,
        )
