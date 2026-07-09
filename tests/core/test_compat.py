"""Unit tests for opencontext_core.compat compatibility helpers."""

from __future__ import annotations

import enum
from datetime import timezone

from opencontext_core.compat import UTC, StrEnum


def test_utc_is_timezone_utc() -> None:
    """UTC constant must equal (and be an instance of) datetime.timezone.utc."""
    assert isinstance(UTC, timezone)
    assert UTC == timezone.utc  # noqa: UP017


def test_strenum_is_subclass_of_enum() -> None:
    """StrEnum must be a subclass of enum.Enum (str-ness covered by members test)."""
    assert issubclass(StrEnum, enum.Enum)


def test_strenum_members_are_strings() -> None:
    """Members of a StrEnum subclass must be plain strings."""

    class Color(StrEnum):
        RED = "red"
        GREEN = "green"

    assert isinstance(Color.RED, str)
    assert Color.RED == "red"
    assert Color.GREEN == "green"
