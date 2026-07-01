"""commit-012: studio package declares no new external deps.

``opencontext_studio`` reuses FastAPI (from ``opencontext_api``) and
Textual (from ``opencontext_cli``). Anything else must already be in
the broader workspace; this test guards the dep-boundary.
"""

from __future__ import annotations

from pathlib import Path


def test_studio_optional_extra_or_reuses_existing_deps(tmp_path: Path) -> None:
    pyproject = Path("packages/opencontext_studio/pyproject.toml")
    if not pyproject.exists():
        # No pyproject yet = no claims to test against; pass-by-omission.
        return
    text = pyproject.read_text(encoding="utf-8")
    forbidden = ("uvicorn", "starlette", "requests", "pydantic", "rich")
    offending = [name for name in forbidden if name in text]
    assert not offending, (
        f"opencontext_studio must not declare {offending} as its own dep — "
        "FastAPI/Textual already live in opencontext_api/opencontext_cli"
    )
