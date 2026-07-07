"""Shared JSON assertions used across acceptance tests."""

from __future__ import annotations

import re
from typing import Any

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+")


def assert_no_ansi(text: str, *, where: str) -> None:
    """Machine output must not carry ANSI styling (CLI_CONTRACT JSON purity)."""
    assert not _ANSI_RE.search(text), f"ANSI escape codes found in {where}: {text[:300]!r}"


def assert_semver(value: str, *, where: str) -> None:
    """A published version string must look like a real semver, never a placeholder."""
    assert _SEMVER_RE.match(value), f"{where}: {value!r} is not a semver version"
    assert value != "0.0.0", f"{where}: placeholder version 0.0.0 (RELEASE_CONTRACT rule 2)"


def assert_error_envelope(payload: Any) -> None:
    """Assert the standard error envelope shape from CLI_CONTRACT.md.

    ``{"ok": false, "status": ..., "error": {"code", "message", "hint"?}}``
    """
    assert isinstance(payload, dict), f"error envelope must be an object, got {type(payload)}"
    assert payload.get("ok") is False, f"error envelope requires ok=false, got {payload!r}"
    assert isinstance(payload.get("status"), str), "error envelope requires a status string"
    error = payload.get("error")
    assert isinstance(error, dict), "error envelope requires an error object"
    code = error.get("code")
    assert isinstance(code, str) and re.fullmatch(r"[A-Z0-9_]+", code), (
        f"error.code must be a stable SCREAMING_SNAKE identifier, got {code!r}"
    )
    assert isinstance(error.get("message"), str) and error["message"], (
        "error.message must be a human-readable string"
    )


def find_secret_leaks(text: str, secrets: list[str]) -> list[str]:
    """Return every seeded secret literal that appears verbatim in *text*."""
    return [secret for secret in secrets if secret in text]
