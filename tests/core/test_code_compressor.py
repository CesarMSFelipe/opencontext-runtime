"""Tests for CodeCompressor — AST-aware code compression."""

from __future__ import annotations

from opencontext_core.compression.code_compressor import CodeCompressionMode, CodeCompressor

_PY = '''\
def greet(name: str) -> str:
    """Return a greeting string."""
    # build message
    message = "Hello, " + name
    return message


class Greeter:
    """Wraps greet."""

    def run(self, name: str) -> str:
        return greet(name)
'''


def test_strip_docstrings_removes_docstrings() -> None:
    cc = CodeCompressor()
    # No language → skips tree-sitter, uses regex fallback reliably
    result = cc.compress(_PY, strip_docstrings=True, strip_comments=False, shorten_locals=False)
    assert "Return a greeting string" not in result
    assert "def greet" in result


def test_strip_comments_removes_hash_comments() -> None:
    cc = CodeCompressor()
    result = cc.compress(
        _PY, language="python", strip_docstrings=False, strip_comments=True, shorten_locals=False
    )
    assert "# build message" not in result
    assert "def greet" in result


def test_strip_comments_keeps_hash_inside_string_literal() -> None:
    # Regression: '#' inside a string is not a comment — must not truncate the line.
    cc = CodeCompressor()
    src = 'url = "http://x # y"  # real comment\nz = 1\n'
    result = cc.compress(
        src, language="python", strip_docstrings=False, strip_comments=True, shorten_locals=False
    )
    assert 'url = "http://x # y"' in result  # string body intact
    assert "# real comment" not in result  # trailing comment removed


def test_strip_comments_keeps_double_slash_inside_string_literal() -> None:
    # Regression: '//' inside a string (a URL) is not a comment.
    cc = CodeCompressor()
    src = 'const u = "http://x"; // trailing\nconst v = 1;\n'
    result = cc.compress(
        src,
        language="javascript",
        strip_docstrings=False,
        strip_comments=True,
        shorten_locals=False,
    )
    assert 'const u = "http://x";' in result
    assert "// trailing" not in result


def test_strip_docstrings_preserves_triple_quoted_data_strings() -> None:
    # Regression: a triple-quoted *value* (SQL) is not a docstring — must survive
    # even on the no-tree-sitter fallback path (language omitted).
    cc = CodeCompressor()
    src = 'config = {\n    "sql": """SELECT * FROM t""",\n}\n'
    result = cc.compress(src, strip_docstrings=True, strip_comments=False, shorten_locals=False)
    assert "SELECT * FROM t" in result


def test_plan_mode_keeps_only_signatures() -> None:
    cc = CodeCompressor()
    result = cc.compress(_PY, language="python", mode=CodeCompressionMode.PLAN)
    assert "def greet" in result
    assert "message = " not in result


def test_act_mode_returns_content_unchanged() -> None:
    cc = CodeCompressor()
    result = cc.compress(_PY, language="python", mode=CodeCompressionMode.ACT)
    # ACT returns content as-is; check key content present and nothing stripped
    assert "message = " in result
    assert "return greet(name)" in result


def test_empty_input_returns_empty() -> None:
    cc = CodeCompressor()
    assert cc.compress("") == ""


def test_shorten_locals_does_not_corrupt_strings_or_spacing() -> None:
    cc = CodeCompressor()
    src = (
        'def greet(username):\n'
        '    message = "hello username"\n'
        '    return compute(username, beta_value)\n'
    )
    out = cc._shorten_locals(src, language="python")
    # The identifier inside the string literal is NOT renamed.
    assert "hello username" in out
    # Punctuation is not space-padded (the old token-rejoin produced "greet ( u )").
    assert "greet (" not in out
    assert "compute (" not in out
    # The code-level local IS renamed (so compression still does its job).
    assert "def greet(username)" not in out
