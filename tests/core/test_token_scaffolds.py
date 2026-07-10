import json
from pathlib import Path

import pytest

from opencontext_cli.main import _tokens
from opencontext_core.dx.tokens import build_token_report, suggest_opencontextignore


def test_token_report_scaffold_shape() -> None:
    report = build_token_report()
    assert report.total_indexable_tokens == 0
    assert "**/dist/**" in suggest_opencontextignore()


@pytest.mark.slow
def test_tokens_tree_view(capsys) -> None:
    _tokens("tree")
    payload = json.loads(capsys.readouterr().out)
    assert payload["view"] == "tree"


def test_token_report_scans_project_root(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hello')\n" * 20, encoding="utf-8")
    (tmp_path / ".opencontextignore").write_text("dist/**\n", encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "bundle.js").write_text("x = 1;\n" * 50, encoding="utf-8")

    report = build_token_report(tmp_path)

    assert report.total_indexable_tokens > 0
    assert any("src/app.py" in entry for entry in report.top_token_files)
    assert any("dist/bundle.js" in entry for entry in report.ignored_token_files)
    assert "**/dist/**" in suggest_opencontextignore(tmp_path)
