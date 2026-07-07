"""Frozen catalog of stable machine-readable CLI error codes (CLI_CONTRACT).

``error.code`` values emitted by stable commands are SCREAMING_SNAKE
identifiers and semver-protected: they are never removed or repurposed within
a major version. ``p0`` codes must carry an actionable ``hint`` at emission
(enforced by :class:`opencontext_cli.contracts.errors.CliContractError`).

The exact set is pinned by ``tests/cli/test_error_code_catalog.py``; adding a
code is additive, renaming or dropping one is a breaking change.
"""

from __future__ import annotations

import re
from typing import Final, NamedTuple

SCREAMING_SNAKE: Final = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$")


class ErrorCodeSpec(NamedTuple):
    """Contract metadata for one stable error code."""

    p0: bool
    description: str


STABLE_ERROR_CODES: Final[dict[str, ErrorCodeSpec]] = {
    "CONFIG_INVALID": ErrorCodeSpec(
        True, "Configuration is missing, unparseable, or fails validation."
    ),
    "ROOT_NOT_FOUND": ErrorCodeSpec(True, "The requested project root does not exist."),
    "TARGET_NOT_FOUND": ErrorCodeSpec(
        True, "No indexed file or symbol matches the requested target."
    ),
    "RUN_NOT_FOUND": ErrorCodeSpec(
        True, "No persisted run or context pack matches the requested run id."
    ),
    "PACK_UNREADABLE": ErrorCodeSpec(
        False, "A persisted context pack exists but could not be read."
    ),
    "TDD_NO_TEST_RUNNER": ErrorCodeSpec(
        True, "TDD strict requires a test runner but none was detected."
    ),
    "TDD_RED_NOT_PROVEN": ErrorCodeSpec(
        True, "TDD strict requires a failing test before mutation."
    ),
    "TDD_TEST_ONLY_EDIT": ErrorCodeSpec(
        True, "TDD strict rejected a mutation that only edits tests."
    ),
    "OPERATION_FAILED": ErrorCodeSpec(
        True, "A stable command failed with a runtime (OpenContext) error."
    ),
    "FILE_NOT_FOUND": ErrorCodeSpec(True, "A required file or directory does not exist."),
    "PERMISSION_DENIED": ErrorCodeSpec(
        True, "The operating system denied access to a required path."
    ),
    "UNEXPECTED_ERROR": ErrorCodeSpec(True, "An unexpected internal error aborted the command."),
}


def is_stable_error_code(code: str) -> bool:
    """True when *code* is part of the frozen stable catalog."""
    return code in STABLE_ERROR_CODES


def requires_hint(code: str) -> bool:
    """True when *code* is a cataloged P0 code (hint mandatory at emission)."""
    spec = STABLE_ERROR_CODES.get(code)
    return bool(spec and spec.p0)
