"""Canonical CLI exit codes and the status -> exit code mapping."""

from __future__ import annotations

from enum import IntEnum
from typing import Final


class ExitCode(IntEnum):
    """Documented process exit codes for every OpenContext command."""

    OK = 0
    FAILURE = 1
    USAGE = 2
    CONFIG_INVALID = 3
    POLICY_BLOCKED = 4
    NEEDS_EXECUTOR = 5
    TDD_STRICT_VIOLATION = 6
    SDD_ARTIFACTS_MISSING = 7
    VERIFICATION_FAILED = 8
    INSTALL_INCOMPLETE = 9


_STATUS_EXIT_CODES: Final[dict[str, ExitCode]] = {
    "passed": ExitCode.OK,
    "not_applicable": ExitCode.OK,
    "failed": ExitCode.FAILURE,
    "blocked": ExitCode.FAILURE,
    "needs_context": ExitCode.FAILURE,
    "cancelled": ExitCode.FAILURE,
    "needs_configuration": ExitCode.CONFIG_INVALID,
    "needs_approval": ExitCode.POLICY_BLOCKED,
    "needs_executor": ExitCode.NEEDS_EXECUTOR,
}


def exit_code_for_status(status: str) -> int:
    """Exit code for a canonical status; unknown statuses fail closed (1)."""
    return int(_STATUS_EXIT_CODES.get(status, ExitCode.FAILURE))
