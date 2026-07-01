"""PR-017 Methodology versioning — schema-style version + regression guard."""

from __future__ import annotations

import re


METHODOLOGY_VERSION_FORMAT = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")


class MethodologyRegression(Exception):
    """Methodology version went backwards — regression blocks the verdict."""


_CURRENT_METHODOLOGY_VERSION = "2026.07.01"


def current_methodology_version() -> str:
    return _CURRENT_METHODOLOGY_VERSION


def validate_methodology_version(version: str) -> None:
    if METHODOLOGY_VERSION_FORMAT.match(version) is None:
        raise ValueError(f"invalid methodology version: {version!r}")


def _parts(v: str) -> tuple[int, int, int]:
    return tuple(int(p) for p in v.split("."))  # type: ignore[return-value]


def bump_methodology_version(baseline: str) -> str:
    """Return a methodology version strictly greater than ``baseline``."""
    y, m, d = _parts(baseline)
    return f"{y}.{m:02d}.{d + 1:02d}"


def regression_check(*, baseline: str, current: str) -> None:
    """Raise if ``current`` is older than ``baseline``."""
    if _parts(current) < _parts(baseline):
        raise MethodologyRegression(
            f"methodology regressed: baseline={baseline}, current={current}"
        )