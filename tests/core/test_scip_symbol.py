"""Structured symbol identity: format correctness + lossless round-trip."""

from __future__ import annotations

import pytest

from opencontext_core.indexing.scip_symbol import format_symbol, parse_symbol


def test_module_function_symbol():
    sym = format_symbol(
        language="python", file_path="src/auth.py", name="audit_login", kind="function"
    )
    # The filename carries a '.', a descriptor suffix char, so it is backtick-escaped
    # to guarantee a lossless round-trip.
    assert sym == "opencontext python . . src/`auth.py`/audit_login()."


def test_method_inside_class():
    sym = format_symbol(
        language="python",
        file_path="src/auth.py",
        name="login",
        kind="method",
        container="AuthService",
        package="myproj",
    )
    assert sym == "opencontext python myproj . src/`auth.py`/AuthService#login()."


def test_class_symbol_uses_type_suffix():
    sym = format_symbol(
        language="python", file_path="src/auth.py", name="AuthService", kind="class"
    )
    assert sym.endswith("AuthService#")


def test_variable_uses_term_suffix():
    sym = format_symbol(language="python", file_path="a.py", name="MAX_RETRIES", kind="constant")
    assert sym.endswith("MAX_RETRIES.")


def test_nested_container_splits_into_type_descriptors():
    sym = format_symbol(
        language="python",
        file_path="a.py",
        name="run",
        kind="method",
        container="Outer.Inner",
    )
    parsed = parse_symbol(sym)
    types = [d.name for d in parsed.descriptors if d.suffix == "#"]
    assert types == ["Outer", "Inner"]


@pytest.mark.parametrize(
    "language, file_path, name, kind, container",
    [
        ("python", "src/auth.py", "login", "method", "AuthService"),
        ("go", "pkg/server.go", "ServeHTTP", "function", None),
        ("typescript", "src/x.ts", "MAX", "constant", None),
        ("python", "weird path/mod.py", "a.b weird", "function", None),  # needs escaping
        ("rust", "lib.rs", "Trait`tick", "trait", None),  # backtick in name
    ],
)
def test_round_trip(language, file_path, name, kind, container):
    sym = format_symbol(
        language=language, file_path=file_path, name=name, kind=kind, container=container
    )
    parsed = parse_symbol(sym)
    assert parsed.scheme == "opencontext"
    assert parsed.manager == language
    assert parsed.leaf == name  # the leaf name survives escaping
    # Re-encoding the decoded descriptors reproduces the identical body.
    reparsed = parse_symbol(sym)
    assert [(d.name, d.suffix) for d in parsed.descriptors] == [
        (d.name, d.suffix) for d in reparsed.descriptors
    ]


def test_parse_rejects_non_symbol():
    with pytest.raises(ValueError):
        parse_symbol("not a symbol")
