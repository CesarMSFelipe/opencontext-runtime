"""Harness tests use local storage mode and tdd=off by default.

TDD-specific tests override the mode via their own config objects.
"""

import pytest


@pytest.fixture(autouse=True)
def _harness_test_defaults(monkeypatch):
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    monkeypatch.setenv("OPENCONTEXT_TDD_MODE", "off")
