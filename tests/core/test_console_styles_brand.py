"""Anti-regression for the CLI brand mark single-source contract."""
from __future__ import annotations

from pathlib import Path

import pytest

DX_DIR = Path(__file__).resolve().parents[2] / "packages/opencontext_core/opencontext_core/dx"
CONSOLE_STYLES = DX_DIR / "console_styles.py"
FORBIDDEN_STRINGS = ("87% token reduction", "13+ agents", "Zero secrets")


@pytest.mark.parametrize("needle", FORBIDDEN_STRINGS)
def test_no_marketing_strings_in_dx(needle: str) -> None:
    offenders = [p for p in DX_DIR.rglob("*.py") if needle in p.read_text(encoding="utf-8")]
    assert offenders == [], f"Forbidden marketing string {needle!r} still in: {offenders}"


def test_console_styles_references_brand_mark() -> None:
    text = CONSOLE_STYLES.read_text(encoding="utf-8")
    assert "README_LOGO_TERMINAL" in text, "console_styles.py must reference README_LOGO_TERMINAL"
    assert "README_LOGO_TERMINAL_COMPACT" in text, "console_styles.py must reference README_LOGO_TERMINAL_COMPACT"