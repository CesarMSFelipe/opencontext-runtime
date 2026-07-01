"""Commit-006: RuntimeApi aux stubs + 11-method contract (amendment A1/A2).

Per commit-006 in the v2 plan, RuntimeApi evolves IN PLACE in
``runtime/api.py`` -- no ``runtime/spine.py`` is created. The three auxiliaries
(``simulate``, ``get_health``, ``decide``) ride alongside the 8 session
methods (the 9th ``status`` lands in commit-017).

The single-owner gate (``test_no_duplicate_spine.py``) asserts exactly ONE
``class RuntimeApi`` declaration in ``runtime/`` (A2).
"""

from __future__ import annotations

import inspect

import pytest

from opencontext_core.runtime.api import RuntimeApi

# Aux stubs + the 8 session methods already in api.py. Commit-017 adds the
# 9th (``status``) and re-parametrizes this list.
_METHOD_NAMES = [
    # aux stubs (commit-006)
    "simulate",
    "get_health",
    "decide",
    # session API (8 of 9 -- status lands in commit-017)
    "start_session",
    "run",
    "next",
    "observe",
    "apply",
    "inspect",
    "resume",
    "archive",
]


def test_runtime_api_method_contracts(tmp_path) -> None:
    """Every name on the surface exists on RuntimeApi and is callable.

    Aux stubs raise ``NotImplementedError`` until they are wired; session
    methods are full implementations. The test asserts *existence* -- a
    regression guard for amendment A1 (9-method session-first contract) and
    A2 (single-owner, in-place evolution).
    """
    api = RuntimeApi(tmp_path)
    for name in _METHOD_NAMES:
        assert hasattr(api, name), f"RuntimeApi missing method: {name}"
        assert callable(getattr(api, name)), f"RuntimeApi.{name} is not callable"


def test_aux_stubs_raise_not_implemented(tmp_path) -> None:
    """The three aux stubs (commit-006) raise ``NotImplementedError``.

    They are declared in this commit as NotImplementedError stubs; real
    bodies land in follow-up work.
    """
    api = RuntimeApi(tmp_path)
    # ``simulate`` and ``decide`` take a positional argument; ``get_health``
    # takes none. Pass a dummy for the ones that need one.
    cases = (
        ("simulate", {"plan": "x"}),
        ("get_health", ()),
        ("decide", {"prompt": "x"}),
    )
    for name, args in cases:
        method = getattr(api, name)
        with pytest.raises(NotImplementedError):
            method(*args)


def test_runtime_api_is_single_class_in_runtime_module(tmp_path) -> None:
    """Exactly ONE ``class RuntimeApi`` declaration in ``runtime/api.py``.

    Amendment A2 forbids a parallel ``runtime/spine.py``. The gate is a
    static check via inspect.getsource: the class is defined exactly once
    in this module.
    """
    src = inspect.getsource(RuntimeApi)
    assert src.count("class RuntimeApi") == 1, (
        "RuntimeApi must have exactly one class declaration; "
        "amendment A2 forbids parallel/duplicate classes"
    )


def test_runtimeapi_importable_from_runtime_api_module(tmp_path) -> None:
    """RuntimeApi is importable from its canonical location (no spine.py)."""
    from opencontext_core.runtime.api import RuntimeApi as _Imported

    assert _Imported is RuntimeApi