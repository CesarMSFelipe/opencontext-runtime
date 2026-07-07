"""CLI-ERR-CODES: frozen error-code catalog — SCREAMING_SNAKE, P0 hints, exact set.

CLI_CONTRACT.md: ``error.code`` is a stable SCREAMING_SNAKE identifier
(semver-protected) and P0 errors must carry an actionable hint. This file pins
the catalog exactly so renaming or dropping a code breaks a test, and verifies
every CliContractError raise site in the CLI package uses a catalog code.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# The frozen catalog. Removing or renaming an entry is a breaking change.
EXPECTED_CODES: dict[str, bool] = {
    # code -> p0 (hint required at emission)
    "CONFIG_INVALID": True,
    "ROOT_NOT_FOUND": True,
    "TARGET_NOT_FOUND": True,
    "RUN_NOT_FOUND": True,
    "PACK_UNREADABLE": False,
    "TDD_NO_TEST_RUNNER": True,
    "TDD_RED_NOT_PROVEN": True,
    "TDD_TEST_ONLY_EDIT": True,
    "OPERATION_FAILED": True,
    "FILE_NOT_FOUND": True,
    "PERMISSION_DENIED": True,
    "UNEXPECTED_ERROR": True,
}


def test_catalog_is_pinned_exact_set() -> None:
    """CLI-ERR-CODES: the stable error-code catalog matches the frozen set exactly."""
    from opencontext_cli.contracts.error_codes import STABLE_ERROR_CODES

    assert {code: spec.p0 for code, spec in STABLE_ERROR_CODES.items()} == EXPECTED_CODES


def test_catalog_codes_are_screaming_snake() -> None:
    """CLI-ERR-CODES: every catalog code is a SCREAMING_SNAKE identifier."""
    from opencontext_cli.contracts.error_codes import SCREAMING_SNAKE, STABLE_ERROR_CODES

    bad = [code for code in STABLE_ERROR_CODES if not SCREAMING_SNAKE.match(code)]
    assert not bad, f"non-SCREAMING_SNAKE error codes: {bad}"


def test_catalog_entries_carry_descriptions() -> None:
    """CLI-ERR-CODES: each catalog entry documents what the code means."""
    from opencontext_cli.contracts.error_codes import STABLE_ERROR_CODES

    empty = [code for code, spec in STABLE_ERROR_CODES.items() if not spec.description.strip()]
    assert not empty, f"catalog codes without a description: {empty}"


def test_p0_code_without_hint_is_rejected() -> None:
    """CLI-ERR-CODES: constructing a P0 contract error without a hint fails fast."""
    from opencontext_cli.contracts.errors import CliContractError

    with pytest.raises(ValueError, match="hint"):
        CliContractError("ROOT_NOT_FOUND", "missing root")


def test_p0_code_with_hint_constructs() -> None:
    """CLI-ERR-CODES: a P0 code with a hint constructs and keeps envelope shape."""
    from opencontext_cli.contracts.errors import CliContractError

    err = CliContractError("ROOT_NOT_FOUND", "missing root", hint="Check the path.")
    envelope = err.to_envelope()
    assert envelope["error"]["code"] == "ROOT_NOT_FOUND"
    assert envelope["error"]["hint"] == "Check the path."


def test_non_p0_catalog_code_allows_missing_hint() -> None:
    """CLI-ERR-CODES: non-P0 catalog codes may omit the hint."""
    from opencontext_cli.contracts.errors import CliContractError

    err = CliContractError("PACK_UNREADABLE", "cannot read pack")
    assert err.to_envelope()["error"]["code"] == "PACK_UNREADABLE"


def test_non_catalog_code_still_constructs() -> None:
    """CLI-ERR-CODES: preview/internal surfaces may raise ad-hoc codes (no promise)."""
    from opencontext_cli.contracts.errors import CliContractError

    err = CliContractError("SOME_PREVIEW_CODE", "experimental failure")
    assert err.to_envelope()["error"]["code"] == "SOME_PREVIEW_CODE"


def test_cli_package_raise_sites_use_catalog_codes() -> None:
    """CLI-ERR-CODES: every literal CliContractError code in the CLI package is cataloged."""
    import opencontext_cli
    from opencontext_cli.contracts.error_codes import SCREAMING_SNAKE, STABLE_ERROR_CODES

    package_root = Path(opencontext_cli.__file__).parent
    pattern = re.compile(r'CliContractError\(\s*"([^"]+)"')
    found: dict[str, list[str]] = {}
    for source in package_root.rglob("*.py"):
        for code in pattern.findall(source.read_text(encoding="utf-8")):
            found.setdefault(code, []).append(str(source.relative_to(package_root)))

    assert found, "expected at least one CliContractError raise site in the CLI package"
    not_snake = {c: p for c, p in found.items() if not SCREAMING_SNAKE.match(c)}
    assert not not_snake, f"lowercase/non-contract error codes in source: {not_snake}"
    uncataloged = {c: p for c, p in found.items() if c not in STABLE_ERROR_CODES}
    assert not uncataloged, f"raise sites using uncataloged codes: {uncataloged}"
